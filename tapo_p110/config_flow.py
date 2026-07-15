"""Config flow for Tapo P110."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

from .const import DOMAIN
from .tpap_client import TapoP110Client, TapoAuthError, TapoConnectionError

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class TapoP110ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tapo P110."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            # Validate connection
            client = TapoP110Client(host, username, password)
            try:
                info = await self.hass.async_add_executor_job(
                    client.discover_and_handshake
                )
            except TapoAuthError:
                errors["base"] = "invalid_auth"
            except TapoConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                # Use MAC as unique id
                mac = info.get("mac", "").replace(":", "").replace("-", "")
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured()

                title = f"Tapo P110 ({host})"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_HOST: host,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )