## ADDED Requirements

### Requirement: TPAP client unit tests
The repository MUST contain offline, deterministic unit tests for `tpap_client.py` covering the protocol/crypto surface, with HTTP I/O mocked at the `urllib.request.urlopen` seam.

#### Scenario: SPAKE2+ derivation reproduces recorded vector
- **WHEN** the SPAKE2+ derivation functions are invoked with a recorded test fixture (client keypair, server public, password-derived `w`/`h`)
- **THEN** the computed `L`, `Z`, `V`, confirmation keys, session key, and base nonce match the recorded vector exactly

#### Scenario: AES-CCM nonce sequencing
- **WHEN** `_send_request` is called multiple times in sequence within a session
- **THEN** each request's nonce is `base_nonce[:-4] + pack(">I", seq)` with `seq` incrementing by 1 per successful request
- **AND** the response nonce is derived from the response's leading 4-byte sequence number, not the request's

#### Scenario: 403 triggers single re-handshake retry
- **WHEN** `_send_request` receives an HTTP 403 and `_retried` is `False`
- **THEN** the session is cleared (`_ds_url = None`), a re-handshake occurs, and the request is retried exactly once
- **AND** the retried call is made with `_retried=True`

#### Scenario: Repeated 403 raises TapoConnectionError
- **WHEN** `_send_request` receives an HTTP 403 and `_retried` is already `True`
- **THEN** `TapoConnectionError` is raised (no unbounded recursion)

#### Scenario: Decrypt failure triggers single re-handshake retry
- **WHEN** the response decrypt step raises and `_retried` is `False`
- **THEN** the session is cleared, a re-handshake occurs, and the request is retried exactly once

#### Scenario: Repeated decrypt failure raises TapoConnectionError
- **WHEN** the response decrypt step raises and `_retried` is `True`
- **THEN** `TapoConnectionError` is raised

#### Scenario: Auth error codes map to TapoAuthError
- **WHEN** a decrypted response has `error_code` of `-2202` or `-2203`
- **THEN** `TapoAuthError` is raised

#### Scenario: No-session request raises TapoConnectionError
- **WHEN** `_send_request` is called and `_ds_url` or `_seq` is `None` after `_ensure_session`
- **THEN** `TapoConnectionError` is raised without attempting encryption

### Requirement: get_all_data atomic-vs-best-effort semantics
`get_all_data` MUST treat `device_info` as atomic (failure aborts the whole call) and the 9 other endpoints as best-effort (per-call exceptions are swallowed except `TapoAuthError`).

#### Scenario: device_info failure aborts
- **WHEN** the `get_device_info` request raises any exception
- **THEN** `get_all_data` propagates that exception and returns no partial dict

#### Scenario: best-effort endpoint failure is swallowed
- **WHEN** one of the 9 best-effort endpoints (energy_usage, emeter_data, device_usage, device_time, led_info, auto_update_info, auto_off_config, protection_power, max_power) raises a non-auth exception
- **THEN** `get_all_data` omits that key from the returned dict and continues to the next endpoint

#### Scenario: best-effort TapoAuthError is not swallowed
- **WHEN** one of the 9 best-effort endpoints raises `TapoAuthError`
- **THEN** `get_all_data` re-raises it (auth failure is not best-effort)

### Requirement: Setter preservation re-reads
Setters that modify one field of a multi-field device config MUST re-read the current config first and preserve the unchanged fields.

#### Scenario: set_auto_update preserves time and random_range
- **WHEN** `set_auto_update(enable)` is called
- **THEN** `get_auto_update_info` is called first, and the `set_auto_update_info` request includes the existing `time` and `random_range` values (falling back to 180/120 if absent)

#### Scenario: set_auto_off_enabled preserves delay_min
- **WHEN** `set_auto_off_enabled(enable)` is called
- **THEN** `get_auto_off_config` is called first, and the `set_auto_off_config` request includes the existing `delay_min` (fallback 120)

#### Scenario: set_auto_off_minutes preserves enable
- **WHEN** `set_auto_off_minutes(delay_min)` is called
- **THEN** `get_auto_off_config` is called first, and the `set_auto_off_config` request includes the existing `enable` (fallback False)

#### Scenario: set_power_protection_enabled preserves threshold
- **WHEN** `set_power_protection_enabled(True)` is called and the current threshold is 0
- **THEN** `get_max_power` is called and the threshold defaults to its `max_power` (fallback 3580)
- **WHEN** `set_power_protection_enabled(False)` is called
- **THEN** the current threshold is preserved in the request with `enabled: False`

#### Scenario: set_power_protection_threshold zero disables
- **WHEN** `set_power_protection_threshold(0)` is called
- **THEN** the request sends `{"enabled": False, "protection_power": 0}`
- **WHEN** `set_power_protection_threshold(500)` is called
- **THEN** the request sends `{"enabled": True, "protection_power": 500}`

### Requirement: Coordinator error-mapping invariants
The repository MUST contain unit tests for `TapoP110DataCoordinator` asserting the error-mapping contract, using a mock `TapoP110Client` (no device I/O).

#### Scenario: TapoAuthError maps to ConfigEntryAuthFailed
- **WHEN** the coordinator's `_async_update_data` calls `client.get_all_data` and it raises `TapoAuthError`
- **THEN** the coordinator raises `ConfigEntryAuthFailed`
- **AND** `client.shutdown()` is called before raising

#### Scenario: TapoConnectionError maps to UpdateFailed
- **WHEN** `client.get_all_data` raises `TapoConnectionError`
- **THEN** the coordinator raises `UpdateFailed`
- **AND** `client.shutdown()` is called before raising

#### Scenario: Unknown exception maps to UpdateFailed
- **WHEN** `client.get_all_data` raises any other `Exception`
- **THEN** the coordinator raises `UpdateFailed`
- **AND** `client.shutdown()` is called before raising

#### Scenario: Empty data maps to UpdateFailed
- **WHEN** `client.get_all_data` returns an empty dict (`{}`)
- **THEN** the coordinator raises `UpdateFailed` with a "No data returned" message
- **AND** `client.shutdown()` is NOT called (no error occurred)

#### Scenario: Successful data is returned
- **WHEN** `client.get_all_data` returns a non-empty dict
- **THEN** the coordinator returns that dict as `data` without raising

### Requirement: Tests are offline and deterministic
All unit tests MUST run without network access, real devices, or real Home Assistant setup, and MUST be deterministic across repeated runs.

#### Scenario: No network required
- **WHEN** the test suite runs with network access disabled
- **THEN** all tests pass

#### Scenario: Deterministic across runs
- **WHEN** the test suite is run repeatedly
- **THEN** results are identical every run (no flaky tests, no time-dependent assertions without a frozen clock)