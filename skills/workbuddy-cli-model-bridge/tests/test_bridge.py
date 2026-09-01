from __future__ import annotations

import argparse
import base64
import contextlib
import importlib.util
import io
import json
import os
import stat
import struct
import tempfile
import threading
import unittest
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "bridge.py"
SPEC = importlib.util.spec_from_file_location("workbuddy_bridge", SCRIPT)
BRIDGE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(BRIDGE)


class FakeProxyHandler(BaseHTTPRequestHandler):
    models = [
        {"id": "gpt-5.6-sol", "owned_by": "codex"},
        {"id": "gpt-5.6-sol-fast", "owned_by": "codex"},
        {"id": "grok-4.5", "owned_by": "xai"},
        {"id": "gemini-3.6-flash", "owned_by": "antigravity"},
    ]
    fail_images = False
    fail_required = False
    fail_output_limit = False
    requests: list[dict] = []

    def log_message(self, *_args):
        return

    def send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/v1/models":
            self.send_json({"object": "list", "data": self.models})
            return
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        self.requests.append(payload)
        if self.fail_required:
            self.send_json({"error": {"message": "required route failed"}}, 502)
            return
        if self.fail_output_limit and payload.get("max_tokens", 0) > 32:
            self.send_json({"error": {"message": "output limit rejected"}}, 400)
            return
        if payload.get("stream"):
            body = b'data: {"choices":[{"delta":{"content":"OK"}}]}\n\ndata: [DONE]\n\n'
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        content = payload.get("messages", [{}])[0].get("content")
        if self.fail_images and isinstance(content, list):
            self.send_json({"error": {"message": "images unsupported"}}, 400)
            return
        if isinstance(content, list):
            self.send_json(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "LEFT=RED_SQUARE;RIGHT=BLUE_CIRCLE",
                            }
                        }
                    ]
                }
            )
            return
        if payload.get("tools"):
            self.send_json(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {"name": "bridge_probe", "arguments": '{"value":"ok"}'},
                                    }
                                ],
                            }
                        }
                    ]
                }
            )
            return
        self.send_json({"choices": [{"message": {"role": "assistant", "content": "OK"}}]})


class BridgeTests(unittest.TestCase):
    def setUp(self):
        FakeProxyHandler.fail_images = False
        FakeProxyHandler.fail_required = False
        FakeProxyHandler.fail_output_limit = False
        FakeProxyHandler.requests = []

    def make_home(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        home = Path(temp.name)
        (home / ".workbuddy").mkdir()
        (home / ".workbuddy/models.json").write_text("[]\n", encoding="utf-8")
        return temp, home

    @contextlib.contextmanager
    def fake_proxy(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeProxyHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def sync_args(self, home: Path, proxy_url: str, **overrides):
        values = {
            "providers": "codex",
            "home": str(home),
            "proxy_url": proxy_url,
            "workbuddy": ".workbuddy/models.json",
            "models_file": None,
            "skip_probes": False,
            "apply": True,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_all_bundled_provider_manifests_validate(self):
        for path in sorted((Path(__file__).parents[1] / "providers").glob("*.json")):
            with self.subTest(provider=path.name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual([], BRIDGE.validate_provider(payload, source=path.name))

    def test_manifest_rejects_shell_shaped_login_flag(self):
        provider = json.loads((Path(__file__).parents[1] / "providers/codex.json").read_text(encoding="utf-8"))
        provider["cliproxy"]["login_flag"] = "--codex-login; curl bad.example"
        errors = BRIDGE.validate_provider(provider)
        self.assertTrue(any("login_flag" in error for error in errors))

    def test_manifest_rejects_non_object_and_path_traversal(self):
        self.assertTrue(any("object" in error for error in BRIDGE.validate_provider([])))
        provider = json.loads((Path(__file__).parents[1] / "providers/codex.json").read_text(encoding="utf-8"))
        provider["cli"]["auth_hints"] = ["../outside/auth.json"]
        errors = BRIDGE.validate_provider(provider)
        self.assertTrue(any("auth_hints" in error for error in errors))

    def test_manifest_rejects_invalid_exact_model_limits(self):
        provider = json.loads((Path(__file__).parents[1] / "providers/codex.json").read_text(encoding="utf-8"))
        provider["models"][0]["limits_by_model"] = {"gpt-5.6-sol": {"maxInputTokens": 0}}
        errors = BRIDGE.validate_provider(provider)
        self.assertTrue(any("maxInputTokens" in error for error in errors))

    def test_manifest_rejects_shared_token_limits(self):
        provider = json.loads((Path(__file__).parents[1] / "providers/codex.json").read_text(encoding="utf-8"))
        provider["models"][0]["workbuddy"]["maxInputTokens"] = 123000
        errors = BRIDGE.validate_provider(provider)
        self.assertTrue(any("unknown keys" in error and "maxInputTokens" in error for error in errors))

    def test_manifest_rejects_unsafe_catalog_path_and_non_https_source(self):
        provider = json.loads((Path(__file__).parents[1] / "providers/codex.json").read_text(encoding="utf-8"))
        provider["model_catalogs"][0]["path"] = "../auth.json"
        provider["models"][0]["limits_by_model"]["gpt-5.6-sol"]["sources"]["maxInputTokens"] = "file:///tmp/spec"
        errors = BRIDGE.validate_provider(provider)
        self.assertTrue(any("without traversal" in error for error in errors))
        self.assertTrue(any("https URL" in error for error in errors))
        provider["model_catalogs"][0]["path"] = ".example/auth.json"
        errors = BRIDGE.validate_provider(provider)
        self.assertTrue(any("non-credential model catalog" in error for error in errors))

    def test_proxy_url_loopback_guard_accepts_loopback(self):
        for url in ("http://127.0.0.1:8317", "http://localhost:8317", "http://[::1]:8317", "https://127.0.0.1/"):
            with self.subTest(url=url):
                self.assertEqual(BRIDGE.validate_loopback_url(url), url)

    def test_proxy_url_loopback_guard_rejects_remote(self):
        for url in ("http://192.168.1.5:8317", "https://example.com/v1", "http://10.0.0.1:8317", "ftp://127.0.0.1"):
            with self.subTest(url=url):
                with self.assertRaises(BRIDGE.BridgeError):
                    BRIDGE.validate_loopback_url(url)

    def test_yaml_key_merge_preserves_existing_keys(self):
        source = 'host: "127.0.0.1"\napi-keys:\n  - "existing"\ndebug: false\n'
        merged, changed = BRIDGE.ensure_yaml_list_value(source, "api-keys", "new-key")
        self.assertTrue(changed)
        self.assertEqual(["existing", "new-key"], BRIDGE.yaml_list_values(merged, "api-keys"))
        repeated, repeated_change = BRIDGE.ensure_yaml_list_value(merged, "api-keys", "new-key")
        self.assertFalse(repeated_change)
        self.assertEqual(merged, repeated)

    def test_minimal_config_is_loopback_and_contains_one_key(self):
        text = BRIDGE.minimal_config("bridge-key")
        self.assertEqual("127.0.0.1", BRIDGE.top_level_scalar(text, "host"))
        self.assertEqual(["bridge-key"], BRIDGE.yaml_list_values(text, "api-keys"))
        self.assertIn("allow-remote: false", text)

    def test_vision_probe_image_has_large_distinct_shapes(self):
        raw = base64.b64decode(BRIDGE.PROBE_IMAGE_PNG)
        self.assertEqual(b"\x89PNG\r\n\x1a\n", raw[:8])
        offset = 8
        chunks: dict[bytes, list[bytes]] = {}
        while offset < len(raw):
            length = struct.unpack(">I", raw[offset : offset + 4])[0]
            kind = raw[offset + 4 : offset + 8]
            payload = raw[offset + 8 : offset + 8 + length]
            chunks.setdefault(kind, []).append(payload)
            offset += 12 + length
        width, height = struct.unpack(">II", chunks[b"IHDR"][0][:8])
        self.assertEqual((256, 192), (width, height))
        pixels = zlib.decompress(b"".join(chunks[b"IDAT"]))
        stride = 1 + width * 3

        def pixel(x: int, y: int) -> tuple[int, int, int]:
            start = y * stride + 1 + x * 3
            return tuple(pixels[start : start + 3])

        self.assertEqual((224, 48, 48), pixel(64, 96))
        self.assertEqual((45, 88, 220), pixel(192, 96))
        self.assertEqual((255, 255, 255), pixel(128, 20))

    def test_model_selection_prefers_exact_candidate(self):
        providers = BRIDGE.load_providers(Path(tempfile.gettempdir()))
        selected, missing = BRIDGE.select_recommended_models(
            [
                {"id": "gpt-5.6-sol", "owned_by": "codex"},
                {"id": "gpt-9.9-sol", "owned_by": "codex"},
            ],
            [providers["codex"]],
        )
        self.assertEqual("gpt-5.6-sol", selected[0][2]["id"])
        self.assertEqual([], missing)

    def test_route_catalog_context_overrides_official_exact_model_fallback(self):
        temp, home = self.make_home()
        self.addCleanup(temp.cleanup)
        catalog = home / ".codex/cliproxyapi-catalog.json"
        catalog.parent.mkdir()
        catalog.write_text(
            json.dumps({"models": [{"slug": "gpt-5.6-sol", "context_window": 372000}]}),
            encoding="utf-8",
        )
        provider = json.loads((Path(__file__).parents[1] / "providers/codex.json").read_text(encoding="utf-8"))
        settings, sources = BRIDGE.resolved_workbuddy_settings(provider, provider["models"][0], "gpt-5.6-sol", home)
        self.assertEqual(372000, settings["maxInputTokens"])
        self.assertEqual(128000, settings["maxOutputTokens"])
        self.assertEqual("local_route_catalog:cliproxyapi-catalog.json", sources["maxInputTokens"])

    def test_exact_limits_do_not_bleed_into_older_fallback(self):
        temp, home = self.make_home()
        self.addCleanup(temp.cleanup)
        provider = json.loads((Path(__file__).parents[1] / "providers/codex.json").read_text(encoding="utf-8"))
        settings, sources = BRIDGE.resolved_workbuddy_settings(provider, provider["models"][0], "gpt-5.5", home)
        self.assertNotIn("maxInputTokens", settings)
        self.assertNotIn("maxOutputTokens", settings)
        self.assertEqual({}, sources)

    def test_malformed_route_catalog_is_ignored(self):
        temp, home = self.make_home()
        self.addCleanup(temp.cleanup)
        catalog = home / ".codex/cliproxyapi-catalog.json"
        catalog.parent.mkdir()
        catalog.write_text("{not-json", encoding="utf-8")
        provider = json.loads((Path(__file__).parents[1] / "providers/codex.json").read_text(encoding="utf-8"))
        settings, sources = BRIDGE.resolved_workbuddy_settings(provider, provider["models"][0], "gpt-5.6-sol", home)
        self.assertEqual(1050000, settings["maxInputTokens"])
        self.assertEqual(
            "https://developers.openai.com/api/docs/models/gpt-5.6-sol",
            sources["maxInputTokens"],
        )

    def test_provider_declared_toml_catalog_is_generic(self):
        temp, home = self.make_home()
        self.addCleanup(temp.cleanup)
        catalog = home / ".example/models.toml"
        catalog.parent.mkdir()
        catalog.write_text(
            '[model."example-3"]\nmodel = "example-3"\ncontext_window = 333000\nmax_completion_tokens = 12000\n',
            encoding="utf-8",
        )
        provider = {
            "model_catalogs": [
                {
                    "path": ".example/models.toml",
                    "format": "toml",
                    "id_fields": ["model"],
                    "input_fields": ["context_window"],
                    "output_fields": ["max_completion_tokens"],
                }
            ]
        }
        recommendation = {"workbuddy": {"supportsToolCall": False}}
        settings, sources = BRIDGE.resolved_workbuddy_settings(provider, recommendation, "example-3", home)
        self.assertEqual(333000, settings["maxInputTokens"])
        self.assertEqual(12000, settings["maxOutputTokens"])
        self.assertEqual("local_route_catalog:models.toml", sources["maxOutputTokens"])

    def test_provider_catalogs_fill_missing_fields_in_priority_order(self):
        temp, home = self.make_home()
        self.addCleanup(temp.cleanup)
        catalog_dir = home / ".example"
        catalog_dir.mkdir()
        (catalog_dir / "route.json").write_text(
            json.dumps({"models": [{"id": "example-3", "context": 444000}]}),
            encoding="utf-8",
        )
        (catalog_dir / "fallback.json").write_text(
            json.dumps({"models": [{"id": "example-3", "context": 999000, "output": 16000}]}),
            encoding="utf-8",
        )
        provider = {
            "model_catalogs": [
                {"path": ".example/route.json", "input_fields": ["context"]},
                {"path": ".example/fallback.json", "input_fields": ["context"], "output_fields": ["output"]},
            ]
        }
        limits, sources = BRIDGE.route_model_limits(home, provider, "example-3")
        self.assertEqual(444000, limits["maxInputTokens"])
        self.assertEqual(16000, limits["maxOutputTokens"])
        self.assertEqual("local_route_catalog:route.json", sources["maxInputTokens"])
        self.assertEqual("local_route_catalog:fallback.json", sources["maxOutputTokens"])

    def test_bundled_grok_and_gemini_have_exact_limits(self):
        temp, home = self.make_home()
        self.addCleanup(temp.cleanup)
        providers = BRIDGE.load_providers(home)
        cases = (
            ("xai-grok", "grok-4.5-build-local", 500000, 8192),
            ("antigravity", "gemini-3.6-flash", 1048576, 65536),
        )
        for provider_id, model_id, expected_input, expected_output in cases:
            with self.subTest(model=model_id):
                provider = providers[provider_id]
                settings, _ = BRIDGE.resolved_workbuddy_settings(provider, provider["models"][0], model_id, home)
                self.assertEqual(expected_input, settings["maxInputTokens"])
                self.assertEqual(expected_output, settings["maxOutputTokens"])

    def test_merge_preserves_manual_collision_and_stale_managed_entry(self):
        existing = [
            {"id": "manual-model", "name": "manual-model"},
            {"id": "stale-model", "name": "stale-model"},
        ]
        incoming = [
            ("codex", {"id": "manual-model", "name": "replacement"}),
            ("codex", {"id": "new-model", "name": "new-model"}),
        ]
        merged, changes, managed = BRIDGE.merge_workbuddy_models(existing, incoming, {"stale-model"})
        self.assertEqual("manual-model", merged[0]["name"])
        self.assertIn("manual-model", changes["conflicts"])
        self.assertIn("stale-model", changes["stale_preserved"])
        self.assertIn("new-model", managed)

    def test_local_provider_manifest_overrides_bundled_manifest(self):
        temp, home = self.make_home()
        self.addCleanup(temp.cleanup)
        local_dir = BRIDGE.state_paths(home)["providers"]
        local_dir.mkdir(parents=True)
        provider = json.loads((Path(__file__).parents[1] / "providers/codex.json").read_text(encoding="utf-8"))
        provider["display_name"] = "Local Codex Override"
        (local_dir / "codex.json").write_text(json.dumps(provider), encoding="utf-8")
        loaded = BRIDGE.load_providers(home)
        self.assertEqual("Local Codex Override", loaded["codex"]["display_name"])

    def test_live_sync_probes_and_is_idempotent(self):
        temp, home = self.make_home()
        self.addCleanup(temp.cleanup)
        manual = {"id": "manual-model", "name": "manual-model", "apiKey": "manual-secret"}
        (home / ".workbuddy/models.json").write_text(json.dumps([manual]), encoding="utf-8")
        BRIDGE.save_json(
            BRIDGE.state_paths(home)["secret"],
            {"schema_version": 1, "proxy_api_key": "bridge-secret-value-0123456789"},
        )
        with self.fake_proxy() as proxy_url:
            first_output = io.StringIO()
            with contextlib.redirect_stdout(first_output):
                self.assertEqual(0, BRIDGE.cmd_sync(self.sync_args(home, proxy_url)))
            first_report = json.loads(first_output.getvalue())
            self.assertEqual(["gpt-5.6-sol", "gpt-5.6-sol-fast"], first_report["changes"]["added"])
            models = json.loads((home / ".workbuddy/models.json").read_text(encoding="utf-8"))
            self.assertEqual("manual-secret", models[0]["apiKey"])
            self.assertTrue(models[1]["supportsImages"])
            self.assertTrue(models[1]["supportsToolCall"])
            self.assertEqual(1050000, models[1]["maxInputTokens"])
            self.assertEqual(128000, models[1]["maxOutputTokens"])
            self.assertNotIn("bridge-secret-value-0123456789", first_output.getvalue())
            self.assertEqual(0o600, stat.S_IMODE((home / ".workbuddy/models.json").stat().st_mode))
            backups_before = list((home / ".workbuddy").glob("models.json.backup-*"))
            self.assertEqual(1, len(backups_before))
            self.assertEqual(0o600, stat.S_IMODE(backups_before[0].stat().st_mode))
            self.assertEqual([manual], json.loads(backups_before[0].read_text(encoding="utf-8")))
            os.chmod(home / ".workbuddy/models.json", 0o644)
            os.chmod(BRIDGE.state_paths(home)["secret"], 0o644)
            os.chmod(BRIDGE.state_paths(home)["state"], 0o644)

            second_output = io.StringIO()
            with contextlib.redirect_stdout(second_output):
                self.assertEqual(0, BRIDGE.cmd_sync(self.sync_args(home, proxy_url)))
            second_report = json.loads(second_output.getvalue())
            self.assertEqual([], second_report["changes"]["added"])
            self.assertEqual([], second_report["changes"]["updated"])
            self.assertEqual(["gpt-5.6-sol", "gpt-5.6-sol-fast"], second_report["changes"]["unchanged"])
            self.assertEqual(["workbuddy", "bridge_state", "bridge_secret"], second_report["permissions_hardened"])
            self.assertEqual(backups_before, list((home / ".workbuddy").glob("models.json.backup-*")))
            self.assertEqual(0o600, stat.S_IMODE((home / ".workbuddy/models.json").stat().st_mode))

    def test_failed_image_probe_downgrades_only_image_capability(self):
        temp, home = self.make_home()
        self.addCleanup(temp.cleanup)
        BRIDGE.save_json(
            BRIDGE.state_paths(home)["secret"],
            {"schema_version": 1, "proxy_api_key": "bridge-secret-value-0123456789"},
        )
        FakeProxyHandler.fail_images = True
        with self.fake_proxy() as proxy_url:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(0, BRIDGE.cmd_sync(self.sync_args(home, proxy_url)))
        models = json.loads((home / ".workbuddy/models.json").read_text(encoding="utf-8"))
        self.assertFalse(models[0]["supportsImages"])
        self.assertTrue(models[0]["supportsToolCall"])
        report = json.loads(output.getvalue())
        self.assertFalse(report["probes"]["gpt-5.6-sol"]["images"]["ok"])

    def test_required_probe_failure_leaves_workbuddy_unchanged(self):
        temp, home = self.make_home()
        self.addCleanup(temp.cleanup)
        original = '[{"id":"manual","name":"manual"}]\n'
        workbuddy = home / ".workbuddy/models.json"
        workbuddy.write_text(original, encoding="utf-8")
        BRIDGE.save_json(
            BRIDGE.state_paths(home)["secret"],
            {"schema_version": 1, "proxy_api_key": "bridge-secret-value-0123456789"},
        )
        FakeProxyHandler.fail_required = True
        with self.fake_proxy() as proxy_url:
            with self.assertRaisesRegex(BRIDGE.BridgeError, "All recommended models failed"):
                BRIDGE.cmd_sync(self.sync_args(home, proxy_url))
        self.assertEqual(original, workbuddy.read_text(encoding="utf-8"))
        self.assertEqual([], list(workbuddy.parent.glob("models.json.backup-*")))

    def test_unverified_token_limits_block_registration(self):
        temp, home = self.make_home()
        self.addCleanup(temp.cleanup)
        BRIDGE.save_json(
            BRIDGE.state_paths(home)["secret"],
            {"schema_version": 1, "proxy_api_key": "bridge-secret-value-0123456789"},
        )
        provider = json.loads((Path(__file__).parents[1] / "providers/codex.json").read_text(encoding="utf-8"))
        provider.pop("model_catalogs", None)
        for recommendation in provider["models"]:
            recommendation.pop("limits_by_model", None)
        with self.fake_proxy() as proxy_url, mock.patch.object(
            BRIDGE, "load_providers", return_value={"codex": provider}
        ):
            with self.assertRaises(BRIDGE.BridgeError) as raised:
                BRIDGE.cmd_sync(self.sync_args(home, proxy_url))
        self.assertEqual("all_probes_failed", raised.exception.code)
        self.assertTrue(
            all(item["reason"] == "token_limits_unverified" for item in raised.exception.details["skipped"])
        )
        self.assertEqual([], json.loads((home / ".workbuddy/models.json").read_text(encoding="utf-8")))

    def test_rejected_output_limit_blocks_registration(self):
        temp, home = self.make_home()
        self.addCleanup(temp.cleanup)
        BRIDGE.save_json(
            BRIDGE.state_paths(home)["secret"],
            {"schema_version": 1, "proxy_api_key": "bridge-secret-value-0123456789"},
        )
        FakeProxyHandler.fail_output_limit = True
        with self.fake_proxy() as proxy_url:
            with self.assertRaises(BRIDGE.BridgeError) as raised:
                BRIDGE.cmd_sync(self.sync_args(home, proxy_url))
        self.assertEqual("all_probes_failed", raised.exception.code)
        self.assertTrue(
            all(item["reason"] == "output_limit_probe_failed" for item in raised.exception.details["skipped"])
        )
        self.assertEqual([], json.loads((home / ".workbuddy/models.json").read_text(encoding="utf-8")))

    def test_bootstrap_dry_run_plans_clean_home_without_writing(self):
        temp, home = self.make_home()
        self.addCleanup(temp.cleanup)
        args = argparse.Namespace(home=str(home), config=None, apply=False, allow_rebind_local=False)
        output = io.StringIO()
        with mock.patch.object(BRIDGE.platform, "system", return_value="Darwin"), mock.patch.object(
            BRIDGE.shutil, "which", side_effect=lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None
        ), mock.patch.object(BRIDGE, "brew_formula_installed", return_value=False), mock.patch.object(
            BRIDGE, "brew_prefix", return_value=Path("/opt/homebrew")
        ), mock.patch.object(
            BRIDGE, "detect_config", return_value=None
        ), contextlib.redirect_stdout(output):
            self.assertEqual(0, BRIDGE.cmd_bootstrap(args))
        report = json.loads(output.getvalue())
        self.assertEqual("planned", report["status"])
        self.assertIn("brew install cliproxyapi", report["actions"])
        self.assertFalse(BRIDGE.state_paths(home)["secret"].exists())
        self.assertFalse((home / ".cli-proxy-api/config.yaml").exists())

    def test_public_bind_requires_explicit_rebind_approval(self):
        temp, home = self.make_home()
        self.addCleanup(temp.cleanup)
        config = home / ".cli-proxy-api/config.yaml"
        config.parent.mkdir()
        config.write_text('host: "0.0.0.0"\napi-keys:\n  - "existing"\n', encoding="utf-8")
        args = argparse.Namespace(home=str(home), config=str(config), apply=True, allow_rebind_local=False)
        with mock.patch.object(BRIDGE.platform, "system", return_value="Darwin"), mock.patch.object(
            BRIDGE.shutil, "which", side_effect=lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None
        ), mock.patch.object(BRIDGE, "brew_formula_installed", return_value=True), mock.patch.object(
            BRIDGE, "detect_proxy_binary", return_value="/opt/homebrew/bin/cli-proxy-api"
        ):
            with self.assertRaisesRegex(BRIDGE.BridgeError, "loopback-only") as raised:
                BRIDGE.cmd_bootstrap(args)
        self.assertEqual("public_bind_requires_approval", raised.exception.code)
        self.assertIn('host: "0.0.0.0"', config.read_text(encoding="utf-8"))
        self.assertFalse(BRIDGE.state_paths(home)["secret"].exists())

    def test_audit_never_reads_or_prints_auth_file_contents(self):
        temp, home = self.make_home()
        self.addCleanup(temp.cleanup)
        auth_dir = home / ".cli-proxy-api"
        auth_dir.mkdir()
        (auth_dir / "codex-user@example.com.json").write_text('{"access_token":"never-print-this"}', encoding="utf-8")
        config = auth_dir / "config.yaml"
        config.write_text(BRIDGE.minimal_config("configured-key"), encoding="utf-8")
        with mock.patch.object(BRIDGE, "detect_proxy_binary", return_value="/usr/local/bin/cli-proxy-api"), mock.patch.object(
            BRIDGE, "detect_config", return_value=config
        ), mock.patch.object(BRIDGE, "brew_prefix", return_value=None), mock.patch.object(
            BRIDGE.shutil, "which", side_effect=lambda name: "/usr/local/bin/brew" if name == "brew" else None
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                BRIDGE.cmd_audit(argparse.Namespace(home=str(home), config=None, proxy_url="http://127.0.0.1:9"))
        rendered = output.getvalue()
        self.assertNotIn("never-print-this", rendered)
        self.assertNotIn("user@example.com", rendered)
        self.assertIn('"codex": 1', rendered)


if __name__ == "__main__":
    unittest.main()
