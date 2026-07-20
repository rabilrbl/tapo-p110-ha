"""Config flow for Tapo P110.

Hub model (v2): one config entry per TP-Link account (username+password) with
N device subentries (one per plug, holding only host).

- ``TapoP110ConfigFlow`` creates/reconfigures the hub (account) entry and
  handles zeroconf discovery.
- ``TapoP110DeviceSubentryFlow`` creates/reconfigures a device subentry under
  an existing hub.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import DOMAIN, SUBENTRY_TYPE_DEVICE
from .tpap_client import TapoAuthError, TapoConnectionError, TapoP110Client

_LOGGER = logging.getLogger(__name__)

STEP_DEVICE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
    }
)


def _sanitize_mac(mac: str) -> str:
    """Strip colons/dashes from a MAC address."""
    return mac.replace(":", "").replace("-", "")


def _decode_nickname(raw: str, fallback: str) -> str:
    """Base64-decode a device nickname, falling back on error."""
    if not raw:
        return fallback
    try:
        return base64.b64decode(raw).decode()
    except Exception:
        return fallback


async def _validate_device(hass: HomeAssistant, host: str, username: str, password: str) -> tuple[str, str]:
    """Handshake against a device and return ``(mac, nickname)``.

    Raises ``vol.Invalid``-style flow errors by re-raising Tapo errors mapped
    to flow error keys; callers catch and set ``errors["base"]``.
    """
    client = TapoP110Client(host, username, password)
    info = await hass.async_add_executor_job(client.discover_and_handshake)
    mac = _sanitize_mac(info.get("mac", ""))
    nickname = _decode_nickname(info.get("nickname", ""), host)
    return mac, nickname


class TapoP110ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a Tapo P110 hub (TP-Link account)."""

    VERSION = 2

    _discovered_host: str | None = None
    _zconf_host: str | None = None
    _zconf_mac: str = ""

    @classmethod
    def async_get_supported_subentry_types(cls, config_entry: Any) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the subentry types supported by this hub entry."""
        return {SUBENTRY_TYPE_DEVICE: TapoP110DeviceSubentryFlow}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """First-time hub setup: account credentials + first device host."""
        errors: dict[str, str] = {}
        # Pre-fill host from zeroconf discovery if present.
        default_host = getattr(self, "_discovered_host", None) or ""

        if user_input is not None:
            host = user_input[CONF_HOST]
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            try:
                mac, nickname = await _validate_device(self.hass, host, username, password)
            except TapoAuthError:
                errors["base"] = "invalid_auth"
            except TapoConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                # Hub unique id = normalized account email.
                await self.async_set_unique_id(username.strip().lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Tapo P110 ({username})",
                    data={CONF_USERNAME: username, CONF_PASSWORD: password},
                    subentries=[
                        {
                            "subentry_type": SUBENTRY_TYPE_DEVICE,
                            "data": {CONF_HOST: host},
                            "title": f"Tapo P110 ({nickname})",
                            "unique_id": mac,
                        }
                    ],
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=default_host or None): str,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        """Handle zeroconf discovery of a tplink* device."""
        host = discovery_info.host
        # Lightweight discover to obtain MAC for dedup (no credentials needed).
        probe = TapoP110Client(host, "", "")
        try:
            info = await self.hass.async_add_executor_job(probe.discover_only)
        except TapoConnectionError:
            info = {}
        except Exception:
            _LOGGER.debug("Unexpected error discovering %s", host, exc_info=True)
            info = {}
        mac = _sanitize_mac(info.get("mac", "")) if info else ""
        if mac:
            # Namespace device unique ids so they never collide with the hub's
            # email unique id within the same domain.
            await self.async_set_unique_id(f"dev_{mac}")
            self._abort_if_unique_id_configured()

        hubs = self.hass.config_entries.async_entries(DOMAIN)
        if not hubs:
            # No hub yet → fall through to the full hub+first-device form with
            # the discovered host pre-filled.
            self._discovered_host = host
            return await self.async_step_user()

        # One or more hubs exist → let the user pick which hub to add this
        # device to (or pick none to set up a fresh hub).
        return await self.async_step_zeroconf_select_hub(host=host, mac=mac)

    async def async_step_zeroconf_select_hub(
        self,
        user_input: dict[str, Any] | None = None,
        *,
        host: str | None = None,
        mac: str = "",
    ) -> ConfigFlowResult:
        """Show a hub picker for a discovered device."""
        errors: dict[str, str] = {}
        # Persist across the form submission.
        if host is not None:
            self._zconf_host = host
            self._zconf_mac = mac
        host = self._zconf_host or host or ""
        mac = self._zconf_mac or mac or ""

        hubs = self.hass.config_entries.async_entries(DOMAIN)
        hub_options = {h.entry_id: h.title for h in hubs}
        # Option to set up a brand new hub instead.
        hub_options["__new__"] = "Set up a new hub…"

        if user_input is not None:
            choice = user_input["hub"]
            if choice == "__new__":
                self._discovered_host = host
                return await self.async_step_user()
            hub = self.hass.config_entries.async_get_entry(choice)
            if hub is None:
                errors["base"] = "unknown"
            else:
                username = hub.data[CONF_USERNAME]
                password = hub.data[CONF_PASSWORD]
                try:
                    dev_mac, nickname = await _validate_device(self.hass, host, username, password)
                except TapoAuthError:
                    errors["base"] = "invalid_auth"
                except TapoConnectionError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    errors["base"] = "unknown"
                else:
                    # Dedup against existing subentries on this hub.
                    existing = {s.unique_id for s in hub.subentries.values()}
                    if dev_mac and dev_mac in existing:
                        return self.async_abort(reason="already_configured")
                    subentry = ConfigSubentry(
                        data={CONF_HOST: host},  # type: ignore[reportArgumentType]  # HA stub wants MappingProxyType; dict works at runtime
                        subentry_type=SUBENTRY_TYPE_DEVICE,
                        title=f"Tapo P110 ({nickname})",
                        unique_id=dev_mac or None,
                    )
                    self.hass.config_entries.async_add_subentry(hub, subentry)
                    return self.async_abort(reason="device_added")

        return self.async_show_form(
            step_id="zeroconf_select_hub",
            data_schema=vol.Schema(
                {
                    vol.Required("hub"): vol.In(hub_options),
                }
            ),
            errors=errors,
            description_placeholders={"host": host},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Reconfigure the hub's account credentials (username+password)."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            # Validate against any existing device subentry's host.
            device_host = next(
                (s.data[CONF_HOST] for s in entry.subentries.values() if s.subentry_type == SUBENTRY_TYPE_DEVICE),
                None,
            )
            if device_host is None:
                # No devices yet — store creds unvalidated.
                return self.async_update_and_abort(
                    entry,
                    data={CONF_USERNAME: username, CONF_PASSWORD: password},
                )
            try:
                await _validate_device(self.hass, device_host, username, password)
            except TapoAuthError:
                errors["base"] = "invalid_auth"
            except TapoConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_update_and_abort(
                    entry,
                    data={CONF_USERNAME: username, CONF_PASSWORD: password},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=entry.data.get(CONF_USERNAME, "")): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )


class TapoP110DeviceSubentryFlow(ConfigSubentryFlow):
    """Flow for adding/reconfiguring a Tapo P110 device subentry."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Add a device subentry to the parent hub."""
        errors: dict[str, str] = {}
        entry = self._get_entry()

        if user_input is not None:
            host = user_input[CONF_HOST]
            username = entry.data[CONF_USERNAME]
            password = entry.data[CONF_PASSWORD]
            try:
                mac, nickname = await _validate_device(self.hass, host, username, password)
            except TapoAuthError:
                errors["base"] = "invalid_auth"
            except TapoConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                # Manual dedup against sibling subentries (subentry flows have
                # no _abort_if_unique_id_configured helper).
                existing = {s.unique_id for s in entry.subentries.values()}
                if mac and mac in existing:
                    return self.async_abort(reason="already_configured")
                return self.async_create_entry(
                    title=f"Tapo P110 ({nickname})",
                    data={CONF_HOST: host},
                    unique_id=mac or None,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_DEVICE_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Reconfigure a device subentry's host."""
        errors: dict[str, str] = {}
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        current_host = subentry.data.get(CONF_HOST, "")

        if user_input is not None:
            host = user_input[CONF_HOST]
            username = entry.data[CONF_USERNAME]
            password = entry.data[CONF_PASSWORD]
            try:
                await _validate_device(self.hass, host, username, password)
            except TapoAuthError:
                errors["base"] = "invalid_auth"
            except TapoConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                # The hub entry has an update_listener that reconciles
                # subentries (per-device setup/teardown) on subentry change,
                # so we update without reloading here.
                return self.async_update_and_abort(entry, subentry, data={CONF_HOST: host})

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Required(CONF_HOST, default=current_host): str}),
            errors=errors,
        )
