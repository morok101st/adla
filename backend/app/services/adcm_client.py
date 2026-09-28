import logging
import time

import httpx
from pydantic import TypeAdapter, ValidationError

from app.config import settings
from app.schemas import MissionPayload, UnitPayload


class AdcmError(RuntimeError):
    pass


class MissionNotFound(AdcmError):
    pass


logger = logging.getLogger("adla.adcm")


class AdcmClient:
    def __init__(self) -> None:
        self.base_url = settings.adcm_base_url
        self.timeout = settings.sync_timeout_seconds
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AdcmClient":
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get_json(self, path: str, params: dict[str, int] | None = None) -> object:
        started = time.monotonic()
        logger.info("ADCM fetch started path=%s params=%s", path, params)
        try:
            if self._client is not None:
                response = await self._client.get(path, params=params)
            else:
                async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                    response = await client.get(path, params=params)
            response.raise_for_status()
            payload = response.json()
            logger.info(
                "ADCM fetch completed path=%s status=%s duration_ms=%d",
                path,
                response.status_code,
                (time.monotonic() - started) * 1000,
            )
            return payload
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "ADCM fetch failed path=%s duration_ms=%d error=%s",
                path,
                (time.monotonic() - started) * 1000,
                type(exc).__name__,
            )
            raise AdcmError(f"ADCM-Abruf fehlgeschlagen: {exc}") from exc

    async def get_mission_optional(self, mission_id: int) -> tuple[MissionPayload | None, object]:
        payload = await self._get_json("/open-lineup", {"missionId": mission_id})
        try:
            missions = TypeAdapter(list[MissionPayload]).validate_python(payload)
        except ValidationError as exc:
            raise AdcmError("ADCM-Missionsantwort hat ein unerwartetes Schema") from exc
        mission = next((item for item in missions if item.missionId == mission_id), None)
        return mission, payload

    async def get_mission(self, mission_id: int) -> tuple[MissionPayload, object]:
        mission, payload = await self.get_mission_optional(mission_id)
        if mission is None:
            raise MissionNotFound(f"Mission {mission_id} wurde in ADCM nicht gefunden")
        return mission, payload

    async def get_unit(self, unit_id: int) -> tuple[UnitPayload, object]:
        payload = await self._get_json(f"/open-lineup-unit/{unit_id}")
        try:
            return UnitPayload.model_validate(payload), payload
        except ValidationError as exc:
            raise AdcmError("ADCM-Unit-Antwort hat ein unerwartetes Schema") from exc
