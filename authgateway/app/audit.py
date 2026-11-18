import logging
import time

logger = logging.getLogger("authgateway.audit")


def log_authorization(principal_type: str, principal_id: str, agent_id: str, jti: str | None, result: str) -> None:
    logger.info(
        "authz_check",
        extra={
            "principal_type": principal_type,
            "principal_id": principal_id,
            "agent_id": agent_id,
            "jti": jti,
            "result": result,
            "ts": time.time(),
        },
    )
