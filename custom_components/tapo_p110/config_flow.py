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

STEP_DEVICE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
    }
)


class TapoP110ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tapo P110."""

    VERSION = 1

    def _get_existing_credentials(self) -> tuple[str, str] | None:
        """Check if there's already a configured entry with credentials."""
        entries = self.hass.config_entries.async_entries(DOMAIN)
        for entry in entries:
            username = entry.data.get(CONF_USERNAME)
            password = entry.data.get(CONF_PASSWORD)
            if username and password:
                return username, password
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        # Check if we already have credentials from an existing entry
        existing_creds = self._get_existing_credentials()

        if user_input is not None:
            host = user_input[CONF_HOST]

            if existing_creds:
                username, password = existing_creds
            else:
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

                # Try to decode nickname for title
                import base64
                nickname = host
                raw_nickname = info.get("nickname", "")
                if raw_nickname:
                    try:
                        nickname = base64.b64decode(raw_nickname).decode()
                    except Exception:
                        pass

                return self.async_create_entry(
                    title=f"Tapo P110 ({nickname})",
                    data={
                        CONF_HOST: host,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )

        # Show simplified form if we have existing credentials, full form otherwise
        if existing_creds:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_DEVICE_DATA_SCHEMA,
                errors=errors,
                description_placeholders={
                    "note": "Credentials will be reused from your existing Tapo P110 device."
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfigure to update credentials."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        host = entry.data[CONF_HOST]

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            client = TapoP110Client(host, username, password)
            try:
                await self.hass.async_add_executor_job(
                    client.discover_and_handshake
                )
            except TapoAuthError:
                errors["base"] = "invalid_auth"
            except TapoConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_end(
                    entry_id=entry.entry_id,
                    data={
                        CONF_HOST: host,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME, default=entry.data.get(CONF_USERNAME, "")
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
            description_placeholders={"host": host},
        )