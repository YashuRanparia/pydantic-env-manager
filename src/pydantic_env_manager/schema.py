"""Introspect a BaseSettings class into a flat list of env var specs."""
from __future__ import annotations

import enum
import json
import logging
from dataclasses import dataclass
from typing import Any, List, Optional, Type, get_args

from pydantic import AliasChoices, AliasPath, SecretBytes, SecretStr
from pydantic_settings import BaseSettings

log = logging.getLogger(__name__)
_SECRETS = (SecretStr, SecretBytes)


@dataclass
class VarSpec:
    key: str
    type: str
    default: str  # rendered default; "" when none (or secret)
    required: bool
    secret: bool
    description: str


def resolve_key(cls: Type[BaseSettings], name: str, field: Any) -> Optional[str]:
    """Env var name for a field, or None if it can't be expressed as one."""
    cfg = cls.model_config
    alias = field.validation_alias
    if isinstance(alias, AliasChoices):
        alias = alias.choices[0]
    if isinstance(alias, AliasPath):
        log.warning("skipping %s.%s: AliasPath is not supported", cls.__name__, name)
        return None
    # pydantic-settings does not apply env_prefix to aliased fields
    key = alias if alias else (cfg.get("env_prefix") or "") + name
    return key if cfg.get("case_sensitive") else key.upper()


def _is_secret(annotation: Any) -> bool:
    if isinstance(annotation, type) and issubclass(annotation, _SECRETS):
        return True
    return any(_is_secret(a) for a in get_args(annotation))


def _type_name(annotation: Any) -> str:
    if isinstance(annotation, type) and not get_args(annotation):
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def _render_default(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, enum.Enum):
        value = value.value
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (list, tuple, set, dict)):
        return json.dumps(sorted(value) if isinstance(value, set) else value, default=str)
    return str(value)


def collect(cls: Type[BaseSettings]) -> List[VarSpec]:
    specs = []
    for name, field in cls.model_fields.items():
        key = resolve_key(cls, name, field)
        if key is None:
            continue
        secret = _is_secret(field.annotation)
        required = field.is_required()
        default = "" if secret or required else _render_default(field.get_default(call_default_factory=True))
        specs.append(VarSpec(key, _type_name(field.annotation), default, required, secret, field.description or ""))
    return specs
