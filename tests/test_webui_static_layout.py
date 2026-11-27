from __future__ import annotations

from tests.frontend_runner import frontend_test

import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

from tests.webui_helpers import WebUIStaticTestCase


class WebUIStaticLayoutTests(WebUIStaticTestCase):
    @frontend_test
    def test_shared_theme_preference_runtime_and_shell_bridge(
        self,
    ) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest(
                "node is required for frontend behavior checks"
            )
        module_path = Path(
            "codex_image/webui/frontend/src/theme-preference.ts"
        )
        self.assertTrue(module_path.is_file())
        shell_source = Path(
            "codex_image/webui/frontend/src/shell-ui.ts"
        ).read_text(encoding="utf-8")
        self.assertIn('from "./theme-preference"', shell_source)
        self.assertNotIn(
            'const THEME_STORAGE_KEY = "codex-image-theme-preference"',
            shell_source,
        )
        for name in (
            "normalizeThemePreference",
            "resolveEffectiveTheme",
            "updateThemeSwitcher",
            "applyThemePreference",
            "restoreThemePreference",
            "handleThemeSystemChange",
        ):
            self.assertIn(name, shell_source)

        harness = textwrap.dedent(
            f"""
            const fs = require("fs");
            const ts = require("typescript");
            const vm = require("vm");
            const source = fs.readFileSync(
              {str(module_path)!r},
              "utf8",
            );
            const code = ts.transpileModule(source, {{
              compilerOptions: {{
                module: ts.ModuleKind.CommonJS,
                target: ts.ScriptTarget.ES2020,
              }},
            }}).outputText;
            let mediaHandler = null;
            let removedMediaHandler = null;
            const media = {{
              matches: true,
              addEventListener(_name, handler) {{
                mediaHandler = handler;
              }},
              removeEventListener(_name, handler) {{
                removedMediaHandler = handler;
              }},
            }};
            const window = {{
              matchMedia() {{ return media; }},
              requestAnimationFrame(callback) {{
                callback();
                return 1;
              }},
              cancelAnimationFrame() {{}},
            }};
            const module = {{ exports: {{}} }};
            vm.runInNewContext(code, {{
              module,
              exports: module.exports,
              window,
              requestAnimationFrame: window.requestAnimationFrame,
              cancelAnimationFrame: window.cancelAnimationFrame,
              localStorage: {{
                getItem() {{ return "system"; }},
                setItem() {{}},
              }},
              document: {{
                documentElement: {{
                  dataset: {{}},
                  classList: {{ add() {{}}, remove() {{}} }},
                }},
              }},
              Set,
              String,
            }});
            const m = module.exports;
            const check = (condition, message) => {{
              if (!condition) throw new Error(message);
            }};
            check(
              m.normalizeThemePreference("unknown") === "system",
              "invalid preference was accepted",
            );
            check(
              m.resolveEffectiveTheme("light", true) === "light"
                && m.resolveEffectiveTheme("dark", false) === "dark",
              "explicit themes followed system",
            );
            check(
              m.resolveEffectiveTheme("system", true) === "dark"
                && m.resolveEffectiveTheme("system", false) === "light",
              "system theme did not resolve",
            );
            check(
              m.readThemePreference({{
                getItem() {{ throw new Error("blocked"); }},
              }}) === "system",
              "blocked storage did not fall back",
            );
            m.persistThemePreference("dark", {{
              setItem() {{ throw new Error("blocked"); }},
            }});
            const classes = new Set();
            const root = {{
              dataset: {{}},
              classList: {{
                add(value) {{ classes.add(value); }},
                remove(value) {{ classes.delete(value); }},
              }},
            }};
            m.applyDocumentTheme("system", root, true);
            check(
              root.dataset.theme === "dark"
                && root.dataset.themePreference === "system",
              "document datasets were not applied",
            );
            const buttons = ["system", "light", "dark"].map(
              (value) => ({{
                dataset: {{ themeOption: value }},
                active: false,
                pressed: "",
                classList: {{
                  toggle(_name, active) {{
                    this.owner.active = active;
                  }},
                  owner: null,
                }},
                setAttribute(_name, value) {{
                  this.pressed = value;
                }},
              }}),
            );
            for (const button of buttons) {{
              button.classList.owner = button;
            }}
            let clickHandler = null;
            let removedClickHandler = null;
            const switcher = {{
              querySelectorAll() {{ return buttons; }},
              contains() {{ return true; }},
              addEventListener(_name, handler) {{
                clickHandler = handler;
              }},
              removeEventListener(_name, handler) {{
                removedClickHandler = handler;
              }},
            }};
            m.syncThemeSwitcher(switcher, "dark");
            check(
              buttons[2].active
                && buttons[2].pressed === "true"
                && buttons[0].pressed === "false",
              "switcher state was not synchronized",
            );
            const selected = [];
            const unbind = m.bindThemeSwitcher(
              switcher,
              (value) => selected.push(value),
            );
            clickHandler({{
              target: {{
                closest() {{ return buttons[1]; }},
              }},
            }});
            clickHandler({{
              target: {{
                closest() {{
                  return {{
                    dataset: {{ themeOption: "invalid" }},
                  }};
                }},
              }},
            }});
            unbind();
            check(
              selected.join(",") === "light"
                && removedClickHandler === clickHandler,
              "switcher binding accepted invalid input or did not unbind",
            );
            const stopSystem = m.bindSystemThemePreference(() => {{}});
            stopSystem();
            check(
              mediaHandler && removedMediaHandler === mediaHandler,
              "system listener did not unbind",
            );
            """
        )
        result = subprocess.run(
            [node, "-e", harness],
            cwd=Path.cwd(),
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_system_settings_has_four_tabs_and_network_controls(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        network_styles = Path(
            "codex_image/webui/static/styles/74-api-system-settings.css"
        ).read_text(encoding="utf-8")
        source = Path(
            "codex_image/webui/frontend/src/network-egress-settings.ts"
        ).read_text(encoding="utf-8")

        self.assertEqual(html.count('data-system-settings-tab="'), 4)
        self.assertIn('id="systemSettingsNetworkTab"', html)
        self.assertIn('id="systemSettingsNetworkPanel"', html)
        self.assertIn('id="networkEgressMode"', html)
        self.assertIn('data-network-egress-mode="system"', html)
        self.assertIn('data-network-egress-mode="direct"', html)
        self.assertIn('data-network-egress-mode="custom"', html)
        self.assertIn('id="networkEgressCustomProxy"', html)
        self.assertRegex(
            html,
            r'id="networkEgressTimeoutMinutes"[^>]*type="number"[^>]*min="1"[^>]*max="30"[^>]*step="1"',
        )
        self.assertRegex(
            html,
            r'id="networkEgressRetryCount"[^>]*type="number"[^>]*min="0"[^>]*max="5"[^>]*step="1"',
        )
        self.assertIn('id="networkRequestPolicyHelp"', html)
        self.assertIn('id="networkEgressTimeoutError"', html)
        self.assertIn('id="networkEgressRetryError"', html)
        self.assertIn('id="networkEgressCompatibilityNotice"', html)
        self.assertIn('aria-describedby="networkRequestPolicyHelp networkEgressTimeoutError"', html)
        self.assertIn('aria-describedby="networkRequestPolicyHelp networkEgressRetryError"', html)
        self.assertIn('id="testNetworkEgressButton"', html)
        self.assertIn('id="saveNetworkEgressButton"', html)
        self.assertRegex(
            styles,
            r"\.system-settings-tabs\s*\{[^}]*grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)",
        )
        self.assertIn('fetch("/api/network-egress")', source)
        self.assertIn('fetch("/api/network-egress/test"', source)
        self.assertIn('provider_id: selectedProviderId', source)
        self.assertIn("networkEgressPayloadIsValid", source)
        self.assertIn('url.protocol === "http:" || url.protocol === "https:"', source)
        self.assertIn("!url.username", source)
        self.assertIn("!url.password", source)
        self.assertRegex(
            network_styles,
            r"\.network-request-policy-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)",
        )
        self.assertRegex(
            network_styles,
            r"\.network-egress-panel\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)",
        )
        self.assertRegex(
            network_styles,
            r"@media\s*\(max-width:\s*520px\)[\s\S]*?\.network-request-policy-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)",
        )

    def test_network_egress_mode_selector_uses_shared_sliding_indicator(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        indicator = Path(
            "codex_image/webui/frontend/src/segmented-indicator.ts"
        ).read_text(encoding="utf-8")

        self.assertIn('class="network-egress-mode-selector"', html)
        self.assertIn('".network-egress-mode-selector"', indicator)
        self.assertIn(".network-egress-mode-button", indicator)
        self.assertRegex(
            styles,
            r"\.network-egress-mode-selector \.segmented-indicator\s*\{[^}]*background:\s*var\(--primary\)",
        )
        self.assertRegex(
            styles,
            r"\.network-egress-mode-selector\.segmented-indicator-host \.network-egress-mode-button\.active\s*\{[^}]*background:\s*transparent",
        )
        self.assertRegex(
            styles,
            r"\.network-egress-mode-button:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--focus-ring\)",
        )

    def test_network_egress_current_route_uses_a_neutral_full_surface(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        match = re.search(r"\.network-egress-current-route\s*\{([^}]*)\}", styles)

        self.assertIsNotNone(match)
        declarations = match.group(1)
        self.assertIn("border: 0", declarations)
        self.assertNotIn("border-left", declarations)
        self.assertIn("background: color-mix", declarations)

    def test_sidebar_brand_keeps_product_name_stable_and_model_selector_on_its_own_row(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        sidebar = Path("codex_image/webui/static/styles/10-sidebar.css").read_text(encoding="utf-8")

        self.assertIn('<div class="brand-name">iLab CONJURE</div>', html)
        self.assertIn('id="modelFamilyOptions"', html)
        self.assertLess(html.index('class="brand-name"'), html.index('id="modelFamilyOptions"'))
        self.assertLess(html.index('id="modelFamilyOptions"'), html.index('class="sidebar-search"'))
        self.assertNotIn(".brand-model-context", sidebar)
        self.assertNotIn(".brand-subtitle", sidebar)

    def test_model_family_segments_render_icons_before_short_labels(self) -> None:
        sidebar = Path("codex_image/webui/static/styles/10-sidebar.css").read_text(encoding="utf-8")
        selection = Path("codex_image/webui/frontend/src/model-selection.ts").read_text(encoding="utf-8")

        self.assertIn(
            'icon.className = `model-family-segment-icon model-family-segment-icon-${family.id}`;',
            selection,
        )
        self.assertIn(
            "label.textContent = family.short_name || family.display_name;",
            selection,
        )
        self.assertIn("item.append(icon, label)", selection)
        self.assertIn(".model-family-segment-icon {", sidebar)
        self.assertIn(".model-family-segment-label {", sidebar)

    def test_model_family_marks_are_shared_by_selector_and_history_cards(self) -> None:
        selection = Path("codex_image/webui/frontend/src/model-selection.ts").read_text(encoding="utf-8")
        task_list = Path("codex_image/webui/frontend/src/task-card-view.ts").read_text(encoding="utf-8")
        marks = Path("codex_image/webui/frontend/src/model-family-icons.ts").read_text(encoding="utf-8")
        sidebar = Path("codex_image/webui/static/styles/10-sidebar.css").read_text(encoding="utf-8")
        tasks = Path("codex_image/webui/static/styles/20-tasks.css").read_text(encoding="utf-8")

        self.assertIn("modelFamilyBrandMarkHtml", selection)
        self.assertIn("modelFamilyBrandMarkHtml", task_list)
        self.assertIn('asset: "/static/brand/model-marks/openai.svg"', marks)
        self.assertIn('asset: "/static/brand/model-marks/gemini.svg"', marks)
        self.assertNotIn("grok", marks.lower())
        self.assertIn(".model-family-brand-mark", sidebar)
        self.assertIn(".task-model-family-brand-mark", tasks)
        for asset in ("openai.svg", "gemini.svg"):
            self.assertTrue((Path("codex_image/webui/static/brand/model-marks") / asset).is_file())
        self.assertFalse((Path("codex_image/webui/static/brand/model-marks") / "grok.svg").exists())

    def test_model_family_selector_is_a_subtle_two_segment_control(self) -> None:
        sidebar = Path("codex_image/webui/static/styles/10-sidebar.css").read_text(encoding="utf-8")
        tokens = Path("codex_image/webui/static/styles/00-tokens.css").read_text(encoding="utf-8")

        rail_rule = sidebar.split(".model-family-segments {", 1)[1].split("}", 1)[0]
        sidebar_rail_rule = sidebar.split(".sidebar .model-family-segments {", 1)[1].split("}", 1)[0]
        option_rule = sidebar.split(".model-family-segment {", 1)[1].split("}", 1)[0]
        icon_rule = sidebar.split(".model-family-segment-icon {", 1)[1].split("}", 1)[0]
        indicator_rule = sidebar.split(".model-family-segments .segmented-indicator {", 1)[1].split("}", 1)[0]

        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", rail_rule)
        self.assertIn("--segmented-control-height: 30px", rail_rule)
        self.assertIn("width: 100%", rail_rule)
        self.assertIn("font-size: 13px", option_rule)
        self.assertIn("gap: 6px", option_rule)
        self.assertIn("width: 16px", icon_rule)
        self.assertIn("height: 16px", icon_rule)
        self.assertIn("border: 0", sidebar_rail_rule)
        self.assertIn("background: var(--model-family-rail-surface)", sidebar_rail_rule)
        self.assertIn("border: 0", indicator_rule)
        self.assertIn("background: var(--model-family-indicator-surface)", indicator_rule)
        self.assertNotIn("background: color-mix", indicator_rule)
        self.assertIn("box-shadow: none", indicator_rule)
        self.assertIn("--model-family-rail-surface:", tokens)
        self.assertIn("--model-family-indicator-surface:", tokens)
        self.assertNotIn("model-family-menu", sidebar)
        self.assertNotIn("model-family-button::after", sidebar)

    def test_sidebar_uses_a_role_based_radius_scale(self) -> None:
        tokens = Path("codex_image/webui/static/styles/00-tokens.css").read_text(encoding="utf-8")
        sidebar = Path("codex_image/webui/static/styles/10-sidebar.css").read_text(encoding="utf-8")
        tasks = Path("codex_image/webui/static/styles/20-tasks.css").read_text(encoding="utf-8")
        controls = Path("codex_image/webui/static/styles/40-controls.css").read_text(encoding="utf-8")

        brand_rule = sidebar.split(".brand-mark {", 1)[1].split("}", 1)[0]
        family_rule = sidebar.split(".sidebar .model-family-segments {", 1)[1].split("}", 1)[0]
        family_option_rule = sidebar.split(".model-family-segments .model-family-segment {", 1)[1].split("}", 1)[0]
        search_rule = sidebar.split(".sidebar-search input {", 1)[1].split("}", 1)[0]
        self.assertIn(".sidebar .task-history-batch-button {", sidebar)
        batch_rule = sidebar.split(".sidebar .task-history-batch-button {", 1)[1].split("}", 1)[0]
        group_rule = tasks.split(".task-history-anchor-row,", 1)[1].split("}", 1)[0]
        new_task_rule = controls.split(".brand-new-button {", 1)[1].split("}", 1)[0]

        self.assertIn("--radius: 8px", tokens)
        self.assertIn("--radius-lg: 12px", tokens)
        self.assertIn("--radius-xl: 16px", tokens)
        self.assertIn("border-radius: var(--radius-xl)", brand_rule)
        self.assertIn("border-radius: var(--radius-lg)", family_rule)
        self.assertIn(
            "--segmented-indicator-radius: calc(var(--radius-lg) - var(--segmented-control-padding))",
            family_rule,
        )
        self.assertIn("border-radius: var(--segmented-indicator-radius)", family_option_rule)
        self.assertIn("border-radius: var(--radius-lg)", search_rule)
        self.assertIn("border-radius: var(--radius)", batch_rule)
        self.assertIn("border-radius: var(--radius-lg)", group_rule)
        self.assertIn("border-radius: var(--radius-lg)", new_task_rule)

    def test_model_provider_controls_shrink_without_workspace_overflow(self) -> None:
        sidebar = Path("codex_image/webui/static/styles/10-sidebar.css").read_text(encoding="utf-8")
        layout = Path("codex_image/webui/static/styles/30-layout-top-nav-panels.css").read_text(encoding="utf-8")
        output = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")

        self.assertIn(".model-family-segments", sidebar)
        self.assertIn("min-width: 0", sidebar)
        self.assertIn(".generation-provider-control", layout)
        self.assertIn("text-overflow: ellipsis", layout)
        self.assertIn(".generation-provider-select-shell .themed-select-trigger", layout)
        self.assertIn("max-width: 100%", layout)
        self.assertIn(".concrete-model-field", output)
        self.assertIn("min-width: 0", output)
        self.assertIn("@container workspace (max-width: 899px)", responsive)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", responsive)
        self.assertNotIn("overflow-x: auto", layout[layout.index(".nav-actions"):layout.index(".queue-button")])

    def test_theme_popovers_replace_native_language_and_provider_menus(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        main = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        theme_select = Path("codex_image/webui/frontend/src/themed-select.ts").read_text(encoding="utf-8")
        controls = Path("codex_image/webui/static/styles/40-controls.css").read_text(encoding="utf-8")

        self.assertIn('id="languageSelect"', html)
        self.assertIn('id="generationProviderSelect"', html)
        self.assertIn('initThemedSelectFeature()', main)
        self.assertIn('"languageSelect"', theme_select)
        self.assertIn('"generationProviderSelect"', theme_select)
        self.assertIn('setAttribute("role", "listbox")', theme_select)
        self.assertIn('event.key === "Escape"', theme_select)
        self.assertIn("event.stopPropagation()", theme_select)
        self.assertIn("document.body.append(instance.menu)", theme_select)
        self.assertIn("positionThemedSelectMenu", theme_select)
        self.assertIn(".themed-select-menu", controls)
        self.assertIn(".themed-select-menu.is-portal", controls)
        self.assertIn(".themed-select-menu::-webkit-scrollbar-thumb", controls)
        self.assertRegex(
            controls,
            r"\.themed-select-menu\s*\{[^}]*background:\s*var\(--surface\)[^}]*color:\s*var\(--text\)",
        )

    def test_portaled_theme_menu_reserves_its_trigger_gap_inside_the_viewport(self) -> None:
        theme_select = Path("codex_image/webui/frontend/src/themed-select.ts").read_text(encoding="utf-8")

        positioner = theme_select.split("function positionThemedSelectMenu", 1)[1].split(
            "function positionOpenThemedSelectMenus", 1
        )[0]
        self.assertIn("viewportHeight - rect.bottom - MENU_GAP - MENU_EDGE_GUTTER", positioner)
        self.assertIn("rect.top - MENU_GAP - MENU_EDGE_GUTTER", positioner)

    def test_provider_empty_state_stays_inside_the_selector(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        source = Path("codex_image/webui/frontend/src/provider-selection.ts").read_text(encoding="utf-8")
        layout = Path("codex_image/webui/static/styles/30-layout-top-nav-panels.css").read_text(encoding="utf-8")

        self.assertNotIn('id="generationProviderUnavailable"', html)
        self.assertNotIn("generationProviderUnavailable", source)
        self.assertNotIn(".generation-provider-unavailable", layout)

    def test_model_family_segments_collapse_to_icons_by_container_width(self) -> None:
        sidebar = Path("codex_image/webui/static/styles/10-sidebar.css").read_text(encoding="utf-8")
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")

        self.assertIn("container-type: inline-size", sidebar)
        self.assertIn("container-name: sidebar-shell", sidebar)
        self.assertIn("@container sidebar-shell (max-width: 315px)", sidebar)
        self.assertRegex(
            sidebar,
            r"@container sidebar-shell \(max-width: 315px\)[\s\S]*?\.model-family-segment-label\s*\{[^}]*display:\s*none",
        )
        self.assertRegex(
            responsive,
            r"@media \(max-width: 1180px\)[\s\S]*?\.model-family-segment-label\s*\{[^}]*display:\s*none",
        )


    def test_selected_reference_files_do_not_expand_or_reflow_footer(self) -> None:
        module = Path("codex_image/webui/frontend/src/reference-file-inputs.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/50-image-input-gallery.css").read_text(encoding="utf-8")
        self.assertNotIn("syncReferenceFileWorkspaceClass", module)
        self.assertNotIn("recentReferenceFiles", module)
        self.assertNotRegex(styles, r"\.image-input-footer[^{]*\{[^}]*reference-file-selection")

    def test_reference_file_tiles_share_image_rail_without_recent_file_product_surface(self) -> None:
        module = Path("codex_image/webui/frontend/src/reference-file-inputs.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/50-image-input-gallery.css").read_text(encoding="utf-8")
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")
        self.assertIn(".reference-file-selection.hidden", styles)
        self.assertNotIn("recent-reference-file", styles)
        self.assertNotIn("has-reference-files", styles)
        self.assertNotRegex(styles, r"\.reference-file-selection\s*\{[^}]*position:\s*absolute")
        self.assertNotRegex(styles, r"\.reference-file-selection\s*\{[^}]*overflow-x:\s*auto")
        self.assertRegex(styles, r"\.image-thumb-items\s*,\s*\.reference-file-selection\s*\{[^}]*display:\s*contents")
        self.assertIn("tile.append(icon, name, remove)", module)
        self.assertRegex(
            styles,
            r"\.reference-file-thumb \.reference-file-format-icon\s*\{[^}]*width:\s*44px[^}]*height:\s*50px",
        )
        self.assertNotIn(".reference-file-row", styles)
        self.assertNotRegex(responsive, r"\.reference-file-selection\s*\{[^}]*overflow-y:\s*auto")

    def test_task_notification_settings_are_in_system_settings_storage_tab(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        source = self._task_notifications_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="taskNotificationInApp"', html)
        self.assertIn('id="taskNotificationSystem"', html)
        self.assertIn("站内通知", html)
        self.assertIn("系统通知", html)
        self.assertIn("inApp: true", source)
        self.assertIn("system: false", source)
        self.assertIn("Notification.permission", source)
        self.assertRegex(styles, r"\.notification-options-panel\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.notification-option-row\s*\{[^}]*display:\s*flex")

    def test_task_history_anchor_navigation_layout_contract(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('class="task-history-shell"', html)
        self.assertIn('id="taskHistoryTopAnchors"', html)
        self.assertIn('id="taskHistoryBottomAnchors"', html)
        self.assertRegex(styles, r"\.task-history-shell\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.task-history-shell\s*\{[^}]*flex-direction:\s*column")
        self.assertRegex(styles, r"\.task-history-shell\s*\{[^}]*min-height:\s*0")
        self.assertRegex(styles, r"\.task-history-shell\s*\{[^}]*gap:\s*6px")
        self.assertRegex(styles, r"\.task-history-anchor-rail\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.task-history-current-anchor\s*\{[^}]*flex:\s*0\s+0\s+auto")
        self.assertNotIn("--task-history-scrollbar-offset", styles)
        self.assertRegex(styles, r"\.task-history-anchor-rail-top\s*\{[^}]*padding-top:\s*0")
        self.assertRegex(styles, r"\.task-history-anchor-row\s*,[\s\S]*\.task-group-header-split\s*\{[^}]*border:\s*1px\s+solid\s+var\(--panel-border\)")
        self.assertRegex(styles, r"\.task-group-header-split\s*\{[^}]*background:\s*var\(--surface\)")
        self.assertRegex(styles, r"\.sidebar-content\s*\{[^}]*flex:\s*1")
        self.assertRegex(styles, r"\.sidebar-content\s*\{[^}]*min-height:\s*0")
        self.assertNotIn(".task-history-anchor-overlay", styles)
        self.assertNotIn("--task-history-top-anchor-height", styles)
        self.assertNotIn("--task-history-bottom-anchor-height", styles)
        self.assertRegex(
            styles,
            r"\.task-history-anchor-row\s*,[\s\S]*\.task-group-header-split\s*\{[^}]*transition:",
        )
        self.assertRegex(styles, r"\.task-group-items\s*\{[^}]*transition:")
        self.assertRegex(
            styles,
            r"@media \(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*\.task-history-anchor-row\s*,[\s\S]*\.task-group-header-split\s*,[\s\S]*\.task-group-items\s*,[\s\S]*\.task-card\s*,[\s\S]*\.task-queue-drop-placeholder\s*,[\s\S]*\.task-thumb-output\s*,[\s\S]*\.task-thumb-reference-badge\s*,[\s\S]*\.task-group-toggle\s*,[\s\S]*transition:\s*none",
        )

    def test_sidebar_header_and_task_history_share_visible_content_axis(self) -> None:
        sidebar = Path("codex_image/webui/static/styles/10-sidebar.css").read_text(encoding="utf-8")
        tasks = Path("codex_image/webui/static/styles/20-tasks.css").read_text(encoding="utf-8")
        anchors = Path("codex_image/webui/frontend/src/task-history-anchors.ts").read_text(encoding="utf-8")
        render = Path("codex_image/webui/frontend/src/task-list-render.ts").read_text(encoding="utf-8")
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")

        self.assertRegex(
            sidebar,
            r"\.sidebar\s*\{[^}]*--sidebar-content-inset:\s*12px;",
        )
        self.assertNotIn("--task-history-scrollbar-offset", sidebar)
        self.assertRegex(
            sidebar,
            r"\.sidebar-header\s*\{[^}]*padding:\s*16px\s+var\(--sidebar-content-inset\)\s+10px;",
        )
        self.assertRegex(
            sidebar,
            r"\.task-history-shell\s*\{[^}]*padding:\s*0\s+var\(--sidebar-content-inset\);",
        )
        self.assertRegex(
            html,
            r'id="taskHistoryTopAnchors"[\s\S]*id="taskHistoryCurrentAnchor"[\s\S]*class="sidebar-content"[\s\S]*id="taskList"[\s\S]*id="taskHistoryBottomAnchors"',
        )
        self.assertRegex(
            sidebar,
            r"\.task-history-current-anchor\s*\{[^}]*flex:\s*0\s+0\s+auto",
        )
        self.assertIn("renderExpandedTaskGroupHeader(group", render)
        self.assertIn("renderExpandedTaskGroupBodyShellHtml(group)", render)
        self.assertRegex(
            tasks,
            r"\.task-history-tools\s+\.status-text\s*\{[^}]*padding-inline-start:\s*4px;",
        )
        self.assertNotIn("syncTaskHistoryAnchorInset", anchors)

    def test_motion_tokens_are_defined_and_sidebar_avoids_transition_all(self) -> None:
        tokens = Path("codex_image/webui/static/styles/00-tokens.css").read_text(encoding="utf-8")
        sidebar = Path("codex_image/webui/static/styles/10-sidebar.css").read_text(encoding="utf-8")
        tasks = Path("codex_image/webui/static/styles/20-tasks.css").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("--motion-fast: 140ms ease;", tokens)
        self.assertIn("--motion-base: 180ms ease;", tokens)
        self.assertIn("--motion-height: 220ms ease;", tokens)
        self.assertIn("--motion-base: 180ms ease;", styles)
        self.assertNotRegex(sidebar, r"transition:\s*all")
        self.assertNotRegex(tasks, r"transition:\s*all")
        self.assertNotIn("will-change", tasks)
        self.assertRegex(styles, r"\.task-card\s*\{[^}]*transition:\s*transform var\(--motion-fast\)")
        self.assertRegex(
            styles,
            r"\.task-card:focus-visible \.task-card-swipe-surface\s*\{[^}]*"
            r"outline:\s*2px solid var\(--task-card-focus-ring\)",
        )
        self.assertNotRegex(tasks, r"\.task-card\.active:focus-visible[\s\S]*?\{[^}]*outline:\s*none")
        self.assertRegex(
            styles,
            r"\.sidebar-resize-handle:hover::before[\s\S]*color-mix\(in srgb, var\(--primary\) 34%, transparent\)",
        )
        self.assertNotRegex(tasks, r"rgba\(69,\s*123,\s*102")
        self.assertNotRegex(tasks, r"rgba\(166,\s*70,\s*61")
        self.assertNotRegex(tasks, r"rgba\(47,\s*111,\s*228")
        self.assertNotRegex(tasks, r"rgba\(155,\s*127,\s*79")
        self.assertNotRegex(tasks, r"rgba\(136,\s*157,\s*149")

    def test_main_surface_motion_uses_tokens_and_reduced_motion(self) -> None:
        source_paths = [
            Path("codex_image/webui/static/styles/30-layout-top-nav-panels.css"),
            Path("codex_image/webui/static/styles/40-controls.css"),
            Path("codex_image/webui/static/styles/50-image-input-gallery.css"),
            Path("codex_image/webui/static/styles/60-prompt.css"),
            Path("codex_image/webui/static/styles/70-output-settings.css"),
            Path("codex_image/webui/static/styles/71-preview-results.css"),
            Path("codex_image/webui/static/styles/72-queue-modals.css"),
            Path("codex_image/webui/static/styles/73-gallery-drawer.css"),
            Path("codex_image/webui/static/styles/74-api-system-settings.css"),
            Path("codex_image/webui/static/styles/75-gallery-card-image-editor.css"),
        ]
        source = "\n".join(path.read_text(encoding="utf-8") for path in source_paths)
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotRegex(source, r"transition:\s*all")
        self.assertNotRegex(source, r"\b0\.(?:18|2)s\b")
        self.assertNotRegex(source, r"\b(?:140|160|180|220)ms ease\b")
        self.assertNotRegex(source, r"rgba\(69,\s*123,\s*102")
        self.assertNotRegex(source, r"rgba\(166,\s*70,\s*61")
        self.assertNotRegex(source, r"rgba\(155,\s*127,\s*79")
        self.assertRegex(styles, r"\.primary-button\s*\{[^}]*transition:\s*background var\(--motion-base\)")
        self.assertRegex(styles, r"\.ghost-button\s*\{[^}]*background var\(--motion-base\)")
        self.assertRegex(styles, r"\.segmented-indicator-host\.segmented-indicator-ready \.segmented-indicator\s*\{[^}]*transform var\(--motion-base\)")
        self.assertRegex(styles, r"\.segmented-indicator-host\.segmented-indicator-ready \.segmented-indicator\s*\{[^}]*opacity var\(--motion-fast\)")
        self.assertRegex(styles, r"\.image-input-main\s*\{[^}]*border-color var\(--motion-base\)")
        self.assertRegex(styles, r"\.quick-gallery-item\s*\{[^}]*opacity var\(--motion-base\)")
        self.assertRegex(styles, r"\.resource-sheet\s*\{[^}]*transform var\(--motion-fast\)")
        self.assertRegex(styles, r"\.gallery-grid\s*\{[^}]*transition:\s*height var\(--motion-height\)")
        self.assertRegex(styles, r"\.preview-overlay\s*\{[^}]*transition:\s*opacity var\(--motion-base\)")
        self.assertRegex(
            styles,
            r"@media \(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*\.primary-button[\s\S]*\.upload-tile[\s\S]*\.quick-gallery-item[\s\S]*\.resource-sheet[\s\S]*transition:\s*none",
        )
        self.assertRegex(
            styles,
            r"@media \(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*input\[type=range\]\.slider::-webkit-slider-thumb[\s\S]*\.preview-overlay[\s\S]*\.add-upload-to-gallery[\s\S]*transition:\s*none",
        )

    def test_closed_right_edge_drawers_do_not_cast_page_edge_shadow(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        resource_sheet_block = self._extract_css_block(styles, ".resource-sheet")
        resource_sheet_open_block = self._extract_css_block(styles, ".resource-sheet.open")
        queue_drawer_block = self._extract_css_block(styles, ".queue-drawer")
        queue_drawer_open_block = self._extract_css_block(styles, ".queue-drawer.open")

        self.assertIn("box-shadow: none", resource_sheet_block)
        self.assertIn("box-shadow: -18px 0 44px rgba(var(--shadow-rgb), 0.16)", resource_sheet_open_block)
        self.assertIn("box-shadow: none", queue_drawer_block)
        self.assertIn("box-shadow: -18px 0 60px rgba(var(--shadow-rgb), 0.18)", queue_drawer_open_block)

    def test_recent_reference_assets_are_rendered_and_submitted(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="recentAssetDock"', html)
        self.assertIn('id="recentAssetVisibilityToggle"', html)
        self.assertIn('aria-controls="recentAssetList"', html)
        self.assertRegex(html, r'class="image-input-footer"[\s\S]*id="recentAssetDock"[\s\S]*id="recentAssetList"')
        self.assertRegex(html, r'id="recentAssetDock"[\s\S]*id="quickGalleryDock"[\s\S]*id="galleryManagePanel"')
        self.assertIn("recentAssets: []", script)
        self.assertIn("recentAssetDock: document.querySelector(\"#recentAssetDock\")", script)
        self.assertIn("recentAssetList: document.querySelector(\"#recentAssetList\")", script)
        self.assertIn("recentAssetVisibilityToggle: document.querySelector(\"#recentAssetVisibilityToggle\")", script)
        self.assertIn("refreshRecentAssets();", script)
        self.assertIn("function refreshRecentAssets()", script)
        self.assertIn("function renderRecentAssets(", script)
        self.assertIn("function toggleRecentAssetPreviews()", script)
        self.assertIn('classList.toggle("previews-hidden", recentAssetPreviewsHidden)', script)
        self.assertIn('toggleAttribute("inert", recentAssetPreviewsHidden)', script)
        self.assertIn('setAttribute("aria-expanded", String(!recentAssetPreviewsHidden))', script)
        self.assertIn('els.recentAssetVisibilityToggle?.addEventListener("click", toggleRecentAssetPreviews)', script)
        self.assertIn("function assetSource(item)", script)
        self.assertIn("function referenceAssetInputs()", script)
        self.assertIn("function addReferenceAssetInput(item)", script)
        self.assertIn("function canAddSourceToGallery(source)", script)
        self.assertIn("function galleryImageFileForSource(source)", script)
        self.assertIn('gallery_prompt: galleryContext', script)
        self.assertIn('source.kind === "asset"', script)
        self.assertRegex(script, r"function canAddSourceToGallery\(source\)\s*\{[\s\S]*source\.kind === \"asset\"[\s\S]*sourcePreviewUrl\(source\)")
        self.assertRegex(script, r"async function saveUploadToGallery\(\)\s*\{[\s\S]*await galleryImageFileForSource\(source\)[\s\S]*form\.append\(\"image\", imageFile\)")
        self.assertIn('form.append("reference_asset_ids", source.id)', script)
        self.assertIn('fetch("/api/reference-assets/recent?limit=50"', script)
        self.assertIn("reference_asset_ids: assets.map((source) => source.id)", script)
        self.assertIn("data-reference-asset-delete", script)
        self.assertIn("data-reference-asset-hide", script)
        self.assertIn("function deleteRecentAsset", script)
        self.assertIn("function hideRecentAsset", script)
        self.assertIn('fetch(`/api/reference-assets/${encodeURIComponent(assetId)}`', script)
        self.assertIn('fetch(`/api/reference-assets/${encodeURIComponent(assetId)}/hide`', script)
        self.assertIn('method: "DELETE"', script)
        self.assertIn('method: "POST"', script)
        self.assertIn("function handleRecentAssetWheel", script)
        self.assertIn('els.recentAssetList?.addEventListener("wheel", handleRecentAssetWheel, { passive: false });', script)
        self.assertIn("const nextScrollLeft = Math.min(maxScrollLeft, Math.max(0, list.scrollLeft + wheelDelta));", script)
        self.assertIn("openConfirmPopover(button", script)
        self.assertIn('event.stopPropagation();', script)
        self.assertIn('formatTranslation("recentAssets.hideMessage"', script)
        self.assertIn('formatTranslation("recentAssets.inUse"', script)
        self.assertIn('detail?.code === "reference_asset_in_use"', script)
        self.assertIn("danger: false", script)
        self.assertIn('options.danger === false', script)
        self.assertIn('document.addEventListener(LOCALE_CHANGE_EVENT, () => renderRecentAssets());', script)
        self.assertNotIn("不会影响公用图库或历史任务。", script)
        self.assertNotIn("已加入图像输入的同一图片也会移除", script)
        self.assertIn('translate("imageInput.recentBadge")', script)
        self.assertIn('translate("imageInput.uploadBadge")', script)
        self.assertIn('wrapper.className = `thumb ${source.kind === "gallery" ? "gallery-thumb" : source.kind === "asset" ? "asset-thumb" : "upload-thumb"}${source.missing ? " missing-thumb" : ""}`', script)
        self.assertIn("restoredSources.push(assetSource(source));", script)
        self.assertRegex(styles, r"\.recent-asset-list\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.recent-asset-list\s*\{[^}]*scrollbar-width:\s*none")
        self.assertRegex(styles, r"\.recent-asset-list\s*\{[^}]*-ms-overflow-style:\s*none")
        self.assertRegex(styles, r"\.recent-asset-list\s*\{[^}]*box-sizing:\s*border-box")
        self.assertRegex(styles, r"\.recent-asset-list\s*\{[^}]*padding:\s*4px 4px 0 0")
        self.assertRegex(styles, r"\.recent-asset-dock\.previews-hidden\s+\.recent-asset-list\s*\{[^}]*visibility:\s*hidden")
        self.assertRegex(styles, r"\.recent-asset-visibility-toggle\s*\{[^}]*border:\s*0")
        self.assertRegex(styles, r"\.recent-asset-list::\-webkit-scrollbar\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.recent-asset-button\s*\{[^}]*width:\s*var\(--recent-asset-size\)")
        self.assertRegex(styles, r"\.recent-asset-button\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.recent-asset-button\s+img\s*\{[^}]*object-fit:\s*cover")
        self.assertRegex(styles, r"\.recent-asset-delete\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.recent-asset-delete\s*\{[^}]*right:\s*-4px")
        self.assertRegex(styles, r"\.recent-asset-delete\s*\{[^}]*opacity:\s*0")
        self.assertRegex(styles, r"\.recent-asset-button:hover\s+\.recent-asset-delete\s*,\s*\.recent-asset-button:focus-within\s+\.recent-asset-delete\s*\{[^}]*opacity:\s*1")
        self.assertRegex(styles, r"\.asset-thumb\s*\{[^}]*border-color:")

    def test_api_settings_refresh_updates_top_auth_source_summary(self) -> None:
        provider_source = Path("codex_image/webui/frontend/src/api-provider-settings.ts").read_text(encoding="utf-8")
        refresh_body = provider_source[
            provider_source.index("export async function refreshApiSettings"):
            provider_source.index("export function populateApiSettingsForm")
        ]

        self.assertIn("state.apiSettings = mergeApiProviderKeys(data.settings || {})", refresh_body)
        self.assertIn("populateApiSettingsForm({ preserveEditor: true });", refresh_body)
        self.assertIn("renderAuthSourceAfterProviderChange();", refresh_body)

    def test_sidebar_brand_uses_ilab_conjure_identity(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("<title>iLab CONJURE</title>", html)
        self.assertNotIn("<title>iLab GPT CONJURE</title>", html)
        self.assertIn('<link rel="icon" type="image/svg+xml" href="/static/brand/favicon.svg" />', html)
        self.assertNotIn('<link rel="icon" href="data:," />', html)
        self.assertIn('<div class="brand-lockup">', html)
        self.assertIn('class="brand-mark brand-mark-rabbit"', html)
        self.assertIn('class="brand-rabbit-logo"', html)
        self.assertIn('class="brand-rabbit-fill"', html)
        self.assertIn('class="brand-rabbit-cutout"', html)
        self.assertIn('class="brand-rabbit-spark"', html)
        self.assertIn('<div class="brand-name">iLab CONJURE</div>', html)
        self.assertRegex(html, r'id="modelFamilyOptions"[\s\S]*role="radiogroup"')
        self.assertNotIn('class="brand-subtitle"', html)
        self.assertIn('aria-label="iLab CONJURE"', html)
        self.assertNotIn("GPT-image-2 Studio", html)
        favicon_path = Path("codex_image/webui/static/brand/favicon.svg")
        self.assertTrue(favicon_path.exists())
        favicon_source = favicon_path.read_text(encoding="utf-8")
        self.assertIn('viewBox="0 0 128 128"', favicon_source)
        self.assertIn('fill="#457B66"', favicon_source)
        self.assertIn('fill="#FFFFFF"', favicon_source)
        self.assertNotIn("currentColor", favicon_source)
        self.assertNotIn("sodipodi:", Path("codex_image/webui/static/brand/rabbit-logo.svg").read_text(encoding="utf-8"))
        self.assertNotIn("inkscape:", Path("codex_image/webui/static/brand/rabbit-logo.svg").read_text(encoding="utf-8"))

        self.assertRegex(styles, r"\.brand-mark\s*\{[^}]*width:\s*42px")
        self.assertRegex(styles, r"\.brand-mark\s*\{[^}]*height:\s*42px")
        self.assertRegex(styles, r"\.brand-mark\s*\{[^}]*border-radius:\s*var\(--radius-xl\)")
        self.assertRegex(styles, r"\.brand-rabbit-logo\s*\{[^}]*fill:\s*currentColor")
        self.assertRegex(styles, r"\.brand-rabbit-logo\s*\{[^}]*color:\s*#ffffff")
        self.assertRegex(styles, r"\.brand-rabbit-cutout\s*\{[^}]*fill:\s*#457b66")
        self.assertRegex(styles, r"\.brand-rabbit-spark\s*\{[^}]*stroke-width:\s*1\.55")
        self.assertRegex(styles, r"\.brand-name\s*\{[^}]*font-size:\s*17px")
        self.assertRegex(styles, r"\.model-family-segments\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)")
        self.assertRegex(styles, r"\.model-family-segments\s+\.model-family-segment\s*\{[^}]*font-size:\s*13px")
        self.assertNotIn(".brand-subtitle", styles)
    def test_sidebar_footer_utilities_are_centered(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotIn('id="settingsButton"', html)
        self.assertNotIn("存储设置</button>", html)
        self.assertRegex(html, r'<div class="task-history-tools">\s*<div id="statusText" class="status-text"')
        self.assertRegex(html, r'<div class="task-history-tools">[\s\S]*id="batchManageButton"')
        self.assertRegex(html, r'<div id="batchToolbar" class="batch-toolbar hidden"')
        self.assertRegex(html, r'<div class="sidebar-footer">\s*<div class="sidebar-api-status-holder"')
        self.assertNotIn('class="footer-actions"', html)
        self.assertNotIn('class="api-status-bar"', html)
        self.assertRegex(styles, r"\.sidebar-footer\s*\{[^}]*align-items:\s*center")
        self.assertRegex(styles, r"\.sidebar-footer\s*\{[^}]*text-align:\s*center")
        self.assertRegex(styles, r"\.task-history-tools\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto")
        self.assertRegex(styles, r"\.task-history-batch-button\s*\{[^}]*min-height:\s*30px")
        self.assertRegex(styles, r"\.status-text\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.status-text\s*\{[^}]*max-width:\s*100%")
        self.assertRegex(styles, r"\.status-text\s*\{[^}]*overflow-wrap:\s*anywhere")
        self.assertRegex(styles, r"\.status-text\s*\{[^}]*word-break:\s*break-word")
        self.assertRegex(styles, r"\.status-text\s*\{[^}]*display:\s*-webkit-box")
        self.assertRegex(styles, r"\.status-text\s*\{[^}]*-webkit-line-clamp:\s*3")
        self.assertRegex(styles, r"\.status-text\s*\{[^}]*max-height:\s*4\.5em")
        self.assertRegex(styles, r"\.task-history-tools\s+\.status-text\s*\{[^}]*-webkit-line-clamp:\s*1")
        self.assertRegex(styles, r"\.sidebar-api-status-holder\s*\{[^}]*display:\s*none")
        self.assertNotIn(".footer-actions", styles)
        self.assertNotIn(".api-status-bar", styles)
        self.assertRegex(styles, r"\.version-info\s*\{[^}]*text-align:\s*center")
        self.assertRegex(styles, r"\.version-info\s*\{[^}]*font-size:\s*11px")
        self.assertIn('<span id="versionInfo" class="version-info">', html)
        self.assertRegex(styles, r"\.batch-toolbar\s*\{[^}]*align-self:\s*stretch")
        self.assertRegex(styles, r"\.batch-toolbar\s*\{[^}]*gap:\s*7px")
        self.assertRegex(styles, r"\.batch-toolbar\s*\{[^}]*padding:\s*8px\s+10px")

    def test_app_version_label_is_static_and_has_no_update_flow(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = Path("codex_image/webui/static/app.js").read_text(encoding="utf-8")

        self.assertIn('id="versionLabel"', html)
        self.assertIn("/api/app-version", script)
        self.assertIn("footer.version", script)
        self.assertIn("document.addEventListener(LOCALE_CHANGE_EVENT", script)
        for removed in ('id="versionModal"', 'id="versionUpdateButton"', 'id="versionOnboardingNotice"'):
            self.assertNotIn(removed, html)
        for removed in ("/api/app-version/open-updater", "/api/app-version/dismiss-onboarding", "post_update_onboarding"):
            self.assertNotIn(removed, script)

    def test_workspace_profiles_use_available_container_width(self) -> None:
        base = Path("codex_image/webui/static/styles/01-base.css").read_text(encoding="utf-8")
        layout = Path("codex_image/webui/static/styles/30-layout-top-nav-panels.css").read_text(encoding="utf-8")
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")

        main_wrapper = self._extract_css_block(layout, ".main-wrapper")
        dashboard = self._extract_css_block(layout, ".dashboard")
        self.assertIn(
            "container-type: inline-size",
            main_wrapper,
            "the remaining workspace width must drive its own layout profile",
        )
        self.assertIn("container-name: workspace", main_wrapper)
        self.assertIn("min-height: 0", main_wrapper)
        self.assertRegex(
            self._extract_css_block(base, ".layout-container"),
            r"height:\s*100dvh",
        )
        self.assertIn("width: min(100%, 1760px)", dashboard)
        self.assertIn("padding: 24px", dashboard)
        self.assertIn("gap: 24px", dashboard)

        compact = self._extract_last_css_at_rule(responsive, "@container workspace (max-width: 1100px)")
        self.assertRegex(
            compact,
            r"\.dashboard\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.1fr\)\s+minmax\(320px,\s*0?\.9fr\)",
        )
        stacked = self._extract_css_at_rule(responsive, "@container workspace (max-width: 899px)")
        self.assertRegex(stacked, r"\.dashboard\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")

    def test_compact_shell_and_workspace_profiles_have_separate_authority(self) -> None:
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")

        self.assertNotRegex(
            responsive,
            r"\(min-width:\s*1024px\)",
            "the old desktop width authority must not overlap the compact shell",
        )
        self.assertNotRegex(
            responsive,
            r"@media\s*\(max-width:\s*1024px\)",
            "workspace stacking belongs to the workspace container, not the viewport",
        )
        shell = self._extract_css_at_rule(responsive, "@media (max-width: 1180px)")
        self.assertRegex(shell, r"\.layout-container\s*\{[^}]*flex-direction:\s*column")
        self.assertRegex(shell, r"\.sidebar\s*\{[^}]*width:\s*100%")
        self.assertIn(".sidebar-search", shell)
        self.assertNotRegex(shell, r"\.dashboard\s*\{[^}]*grid-template-columns")
        self.assertNotRegex(shell, r"\.preview-col\s*\{[^}]*height:")
        self.assertIn("@container workspace (max-width: 1100px)", responsive)
        self.assertIn("@container workspace (max-width: 899px)", responsive)

    def test_control_panel_titles_and_labels_use_a_shared_optical_inset(self) -> None:
        layout = Path(
            "codex_image/webui/static/styles/30-layout-top-nav-panels.css"
        ).read_text(encoding="utf-8")
        output = Path(
            "codex_image/webui/static/styles/70-output-settings.css"
        ).read_text(encoding="utf-8")

        self.assertRegex(
            layout,
            r"\.controls-col\s*\{[^}]*--control-label-optical-inset:\s*2px",
        )
        self.assertRegex(
            layout,
            r"\.controls-col \.panel-heading h2,\s*"
            r"\.controls-col \.output-settings-header h2\s*\{[^}]*"
            r"padding-inline-start:\s*var\(--control-label-optical-inset\)",
        )
        self.assertRegex(
            output,
            r"\.controls-col \.output-panel \.field > span\s*\{[^}]*"
            r"padding-inline-start:\s*var\(--control-label-optical-inset\)",
        )
        self.assertNotRegex(
            layout + output,
            r"(?:panel-heading h2|output-settings-header h2|field-label)[^{]*"
            r"\{[^}]*(?:margin-left|transform):",
        )

    def test_compact_navigation_scroll_does_not_clip_notification_center(self) -> None:
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")

        shell = self._extract_css_at_rule(responsive, "@media (max-width: 1180px)")
        self.assertNotRegex(shell, r"\.top-nav\s*\{[^}]*(?:overflow|overflow-x):\s*auto")
        self.assertRegex(shell, r"\.nav-actions\s*\{[^}]*overflow-x:\s*auto")

    def test_responsive_scroll_owners_are_explicit(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        layout = Path("codex_image/webui/static/styles/30-layout-top-nav-panels.css").read_text(encoding="utf-8")
        output = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")
        prompt = Path("codex_image/webui/static/styles/60-prompt.css").read_text(encoding="utf-8")
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")
        shell = Path("codex_image/webui/frontend/src/shell-ui.ts").read_text(encoding="utf-8")

        self.assertNotIn(
            "--controls-col-height",
            shell,
            "CSS grid must be the only preview-height authority",
        )
        self.assertNotIn("setupPreviewPanelHeightSync", shell)
        self.assertNotIn("syncPreviewPanelHeight", shell)
        self.assertNotIn("ResizeObserver", shell)

        dashboard = self._extract_css_block(layout, ".dashboard")
        controls = self._extract_css_block(layout, ".controls-col")
        preview = self._extract_css_block(layout, ".preview-col")
        self.assertIn("min-height: 0", dashboard)
        self.assertIn("overflow-y: auto", dashboard)
        self.assertNotIn("grid-template-rows", dashboard)
        self.assertNotIn("overflow-y", controls)
        self.assertNotIn("height: 100%", controls)
        self.assertRegex(preview, r"height:\s*auto")
        self.assertRegex(preview, r"overflow:\s*hidden")

        stacked = self._extract_css_at_rule(responsive, "@container workspace (max-width: 899px)")
        self.assertRegex(stacked, r"\.dashboard\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)[^}]*align-content:\s*start")
        self.assertRegex(
            stacked,
            r"\.controls-col\s*\{[^}]*max-width:\s*none[^}]*height:\s*auto[^}]*min-height:\s*auto[^}]*overflow:\s*visible",
        )
        self.assertRegex(stacked, r"\.preview-col\s*\{[^}]*height:\s*auto[^}]*min-height:\s*260px[^}]*overflow:\s*visible")
        self.assertRegex(
            stacked,
            r"\.preview-panel\s*\{[^}]*position:\s*relative[^}]*inset:\s*auto[^}]*min-height:\s*260px",
        )

        for title in ("参考输入（可选）", "提示词", "输出设置"):
            self.assertIn(title, html)
        self.assertIn("justify-content: space-between", self._extract_css_block(layout, ".panel-heading"))
        self.assertIn("justify-content: flex-start", self._extract_css_block(prompt, ".prompt-heading-main"))
        self.assertIn("position: relative", self._extract_css_block(output, ".output-settings-header"))
        self.assertNotRegex(
            responsive,
            r"\.controls-col\s+\.output-settings-header\s+h2\s*\{[^}]*position:\s*absolute[^}]*width:\s*1px",
        )

    def test_short_desktop_layout_compacts_sidebar_footer_and_workbench(self) -> None:
        responsive = Path(
            "codex_image/webui/static/styles/80-utilities-responsive.css"
        ).read_text(encoding="utf-8")
        compact = self._extract_css_at_rule(
            responsive,
            "@media (max-height: 1390px) and (min-width: 900px)",
        )

        self.assertRegex(compact, r"\.sidebar-footer\s*\{[^}]*padding:\s*8px\s+12px")
        self.assertRegex(compact, r"\.version-info\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(
            compact,
            r"\.dashboard\s*\{[^}]*--compact-dashboard-padding:\s*clamp\("
            r"[^}]*padding:\s*var\(--compact-dashboard-padding\)",
        )
        self.assertRegex(
            compact,
            r"\.preview-col\s*\{[^}]*height:\s*calc\("
            r"[\s\S]*var\(--compact-dashboard-padding\)",
        )
        self.assertRegex(
            compact,
            r"\.controls-col\s*\{[^}]*--compact-image-panel-height:\s*clamp\("
            r"[\s\S]*--compact-prompt-panel-height:\s*clamp\("
            r"[\s\S]*justify-content:\s*flex-start",
        )
        self.assertRegex(
            compact,
            r"\.controls-col\s+\.image-panel\s*\{[^}]*"
            r"flex:\s*1\s+0\s+auto",
        )
        self.assertRegex(
            compact,
            r"\.controls-col\s+\.prompt-panel\s*\{[^}]*"
            r"flex:\s*1\.15\s+1\s+var\(--compact-prompt-panel-height\)",
        )
        self.assertRegex(
            compact,
            r"\.controls-col\s+\.output-panel\s*\{[^}]*flex:\s*0\s+0\s+auto",
        )
        self.assertRegex(compact, r"\.panel\s*\{[^}]*padding:\s*clamp\(")
        self.assertNotIn("align-content: space-between", compact)
        self.assertNotRegex(
            responsive,
            r"\.controls-col\s+\.panel-heading\s+h2,[\s\S]*"
            r"\.controls-col\s+\.output-settings-header\s+h2\s*\{[^}]*clip:",
        )
        self.assertIn(
            ".controls-col .image-input-workspace {\n    flex: 1 0 auto;",
            compact,
        )
        self.assertIn(
            ".controls-col .prompt-compose {\n    flex: 1 1 0;\n    min-height: 0;",
            compact,
        )
    def test_sidebar_width_can_be_resized_and_persisted(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        script = self._frontend_script_source()

        self.assertIn('<aside id="sidebar" class="sidebar">', html)
        self.assertIn('id="sidebarResizeHandle"', html)
        self.assertIn('id="sidebarResizeShield"', html)
        self.assertIn('class="sidebar-resize-shield"', html)
        self.assertIn('role="separator"', html)
        self.assertIn('aria-label="调整侧栏宽度"', html)
        self.assertIn("sidebar: document.querySelector(\"#sidebar\")", script)
        self.assertIn("sidebarResizeHandle: document.querySelector(\"#sidebarResizeHandle\")", script)
        self.assertIn("sidebarResizeShield: document.querySelector(\"#sidebarResizeShield\")", script)
        self.assertIn("SIDEBAR_WIDTH_STORAGE_KEY", script)
        self.assertIn("restoreSidebarWidth", script)
        self.assertIn("function sidebarWidthFromCss()", script)
        self.assertIn("function currentSidebarWidth()", script)
        self.assertIn("startSidebarResize", script)
        self.assertIn("scheduleSidebarResizeWidth", script)
        self.assertIn("flushSidebarResizeWidth", script)
        self.assertIn("window.requestAnimationFrame(() =>", script)
        self.assertIn("applySidebarWidth(nextWidth, { persist: false });", script)
        self.assertIn("const currentWidth = currentSidebarWidth();", script)
        self.assertIn('(els.sidebar || document.documentElement).style.setProperty("--sidebar-width"', script)
        self.assertNotIn('document.documentElement.style.setProperty("--sidebar-width"', script)
        self.assertIn("const widthOwner = els.sidebar || document.documentElement;", script)
        self.assertIn("els.sidebarResizeShield.hidden = false;", script)
        self.assertIn("els.sidebarResizeShield.hidden = true;", script)
        self.assertNotIn('document.body.classList.add("sidebar-resizing")', script)
        self.assertNotIn('document.body.classList.remove("sidebar-resizing")', script)
        self.assertNotIn("getBoundingClientRect", self._shell_ui_source())
        self.assertNotIn("ResizeObserver", self._shell_ui_source())
        self.assertNotIn("--controls-col-height", self._shell_ui_source())
        self.assertLess(
            script.index("state.sidebarResize = null;", script.index("function finishSidebarResize")),
            script.index("flushSidebarResizeWidth(nextWidth);", script.index("function finishSidebarResize")),
        )
        self.assertIn("localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY", script)
        self.assertRegex(styles, r":root\s*\{[^}]*--sidebar-min-width:\s*280px")
        self.assertRegex(styles, r":root\s*\{[^}]*--sidebar-max-width:\s*520px")
        self.assertRegex(styles, r"\.sidebar\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.sidebar-resize-handle\s*\{[^}]*cursor:\s*col-resize")
        self.assertRegex(styles, r"\.sidebar-resize-shield\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.sidebar-resize-shield\s*\{[^}]*cursor:\s*col-resize")
    def test_webui_brand_name_is_consistent_across_launch_surfaces(self) -> None:
        app_source = Path("codex_image/webui/app.py").read_text(encoding="utf-8")
        launcher_sources = [
            Path("Start WebUI.command").read_text(encoding="utf-8"),
            Path("Start WebUI Debug.command").read_text(encoding="utf-8"),
            Path("Start WebUI.bat").read_text(encoding="utf-8"),
        ]

        self.assertRegex(app_source, r'FastAPI\(\s*title="iLab CONJURE"')
        self.assertIn("<title>iLab CONJURE</title><h1>iLab CONJURE</h1>", app_source)
        self.assertNotIn("iLab GPT CONJURE", app_source)
        self.assertNotIn("GPT-image-2 Studio", app_source)
        for source in launcher_sources:
            self.assertIn("iLab CONJURE", source)
            self.assertNotIn("iLab GPT CONJURE", source)
            self.assertNotIn("GPT-image-2 Studio", source)
    def test_image_input_source_selector_and_hints_are_removed(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()

        self.assertNotIn("来源选择", html)
        self.assertNotIn("最多支持 16 张图片", html)
        self.assertNotIn("最多支持多张参考图；编辑模式至少需要 1 张图片。", script)
    def test_mask_input_is_removed_from_webui(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()

        self.assertNotIn("maskBlock", html)
        self.assertNotIn("maskInput", html)
        self.assertNotIn("maskName", html)
        self.assertNotIn(">Mask<", html)
        self.assertNotIn("maskBlock", script)
        self.assertNotIn("maskInput", script)
        self.assertNotIn("maskName", script)
        self.assertNotIn("setMask", script)
        self.assertNotIn('form.append("mask"', script)
    def test_image_input_uses_quick_gallery_dock(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('class="image-input-workspace"', html)
        self.assertIn('class="image-input-left"', html)
        self.assertIn('class="image-input-footer"', html)
        self.assertIn('class="image-input-actions"', html)
        self.assertIn('class="image-gallery-column"', html)
        self.assertIn('id="imageThumbList"', html)
        image_thumb_list = html[html.index('id="imageThumbList"'):html.index('id="imageUploadSource"')]
        self.assertLess(image_thumb_list.index('id="imageThumbItems"'), image_thumb_list.index('id="referenceFileSelection"'))
        self.assertIn('id="imageUploadSource"', html)
        self.assertIn('id="quickGalleryDock"', html)
        self.assertIn('id="quickGalleryPreview"', html)
        self.assertIn('id="quickGalleryList"', html)
        self.assertIn('id="quickGalleryRail"', html)
        self.assertIn('id="galleryManagePanel"', html)
        self.assertIn('id="galleryManageButton"', html)
        self.assertNotIn('id="galleryManageSummary"', html)
        self.assertNotIn("查看全部", html)
        self.assertIn('class="ghost-button text-sm icon-text-button resource-manage-button gallery-manage-button"', html)
        self.assertRegex(html, r'id="galleryManageButton"[\s\S]*<svg class="button-icon"[\s\S]*<span[^>]*>管理公用库</span>')
        self.assertIn('data-quick-gallery-category="portrait"', html)
        self.assertIn('data-quick-gallery-category="character"', html)
        self.assertIn('data-quick-gallery-category="product"', html)
        self.assertNotIn('id="imageSourceTabs"', html)
        self.assertNotIn('id="inlineGalleryPicker"', html)
        self.assertNotIn('id="inlineGalleryGrid"', html)
        self.assertNotIn('id="gallerySearch"', html)
        self.assertNotIn('id="galleryButtons"', html)
        self.assertNotIn("gallery-picker-row", html)
        self.assertRegex(html, r'<div class="panel-heading">\s*<h2[^>]*>参考输入（可选）</h2>\s*<button id="compactReferencesButton"[^>]*>[^<]*</button>\s*</div>')
        self.assertRegex(html, r'<div class="image-input-footer">[\s\S]*<div class="image-input-actions">[\s\S]*<button id="clearImagesButton"')
        self.assertRegex(html, r'<div class="image-input-footer">[\s\S]*id="recentAssetDock"[\s\S]*id="recentAssetList"')
        self.assertRegex(html, r'<div class="image-gallery-column">[\s\S]*id="quickGalleryDock"[\s\S]*id="galleryManagePanel"')
        self.assertNotRegex(html, r'<div class="image-gallery-column">[\s\S]*id="recentAssetDock"')
        self.assertIn('id="addToGalleryModal"', html)
        self.assertIn("imageUploadSource: document.querySelector(\"#imageUploadSource\")", script)
        self.assertIn("imageThumbList: document.querySelector(\"#imageThumbList\")", script)
        self.assertIn("imageThumbItems: document.querySelector(\"#imageThumbItems\")", script)
        self.assertIn("imageUploaderGrid: document.querySelector(\".image-uploader-grid\")", script)
        self.assertIn("quickGalleryDock: document.querySelector(\"#quickGalleryDock\")", script)
        self.assertIn("quickGalleryPreview: document.querySelector(\"#quickGalleryPreview\")", script)
        self.assertIn("quickGalleryList: document.querySelector(\"#quickGalleryList\")", script)
        self.assertIn("quickGalleryRail: document.querySelector(\"#quickGalleryRail\")", script)
        self.assertIn("galleryManagePanel: document.querySelector(\"#galleryManagePanel\")", script)
        self.assertIn("galleryManageButton: document.querySelector(\"#galleryManageButton\")", script)
        self.assertIn("renderQuickGalleryDock", script)
        self.assertIn("sortGalleryItems", script)
        self.assertIn('localeCompare(rightName, "zh-CN", { numeric: true, sensitivity: "base" })', script)
        self.assertRegex(script, r"function filterGalleryItems\(category = state\.activeGalleryCategory\)\s*\{[\s\S]*sortGalleryItems")
        self.assertNotIn("galleryManageSummary", script)
        self.assertNotIn("renderGalleryManagePanel", script)
        self.assertIn("setQuickGalleryCategory", script)
        self.assertIn("previewQuickGalleryItem", script)
        self.assertIn("hideQuickGalleryPreview", script)
        self.assertIn("scheduleQuickGalleryFocusUpdate", script)
        self.assertIn("updateQuickGalleryFocus", script)
        self.assertIn('quickGalleryList?.addEventListener("scroll", () => call(methods, "scheduleQuickGalleryFocusUpdate"))', script)
        self.assertIn("handleQuickGalleryBoundaryWheel", script)
        self.assertIn("triggerQuickGalleryBounce", script)
        self.assertIn("QUICK_GALLERY_WHEEL_COOLDOWN_MS", script)
        self.assertIn("const QUICK_GALLERY_WHEEL_COOLDOWN_MS = 220;", script)
        self.assertIn('import { prefersReducedMotion } from "./webui-utils";', script)
        self.assertIn("quickGalleryFocusItemId", script)
        self.assertIn("ensureQuickGalleryFocusItem(items)", script)
        self.assertIn("scrollQuickGalleryItemToFocus", script)
        self.assertIn("focusQuickGalleryItem", script)
        self.assertNotIn("scrollQuickGalleryItemToCenter", script)
        self.assertNotIn("centerQuickGalleryItem", script)
        self.assertIn('button.addEventListener("mouseenter", () => previewQuickGalleryItem(button.dataset.quickGalleryUse));', script)
        self.assertIn("focusQuickGalleryItem(button.dataset.quickGalleryUse)", script)
        self.assertNotRegex(
            script,
            r"function previewQuickGalleryItem\(itemId\)\s*\{[\s\S]*focusQuickGalleryItem\(itemId\)[\s\S]*function hideQuickGalleryPreview",
        )
        self.assertIn("const hoveredButton = state.hoveredGalleryItemId", script)
        self.assertIn("const focusButton = hoveredButton || focusedButton || buttons[0];", script)
        self.assertIn("Math.abs(buttons.indexOf(button) - focusIndex)", script)
        self.assertIn("quickGalleryWheelLockTimerId", script)
        self.assertIn('quickGalleryList?.addEventListener("wheel", (event) => call(methods, "handleQuickGalleryBoundaryWheel", event)', script)
        self.assertIn('classList.add("visible")', script)
        self.assertIn('classList.remove("visible")', script)
        self.assertIn("animateGalleryItemToInput", script)
        self.assertIn('behavior: prefersReducedMotion() ? "auto" : behavior', script)
        self.assertIn("if (prefersReducedMotion()) return;", script)
        self.assertIn("filterGalleryItems", script)
        self.assertIn("data-quick-gallery-use", script)
        self.assertIn("addGalleryInput(item)", script)
        self.assertIn("function handleGalleryManageButtonClick()", script)
        self.assertIn('els.galleryManageButton?.addEventListener("click", handleGalleryManageButtonClick)', script)
        self.assertNotIn("imageSourceTabs: document.querySelector", script)
        self.assertNotIn("inlineGalleryPicker: document.querySelector", script)
        self.assertNotRegex(script, r"\bsetImageSource\b")
        self.assertNotIn("state.gallerySearchQuery", script)
        self.assertNotIn("previewQuickGalleryItem(previewItem?.id || null)", script)
        self.assertIn("add-upload-to-gallery", script)
        self.assertIn("/api/gallery", script)
        self.assertRegex(styles, r"\.image-panel\s*\{[^}]*container-type:\s*inline-size")
        self.assertRegex(styles, r"\.image-input-left\s*\{[^}]*container-type:\s*inline-size")
        self.assertRegex(styles, r"\.image-input-workspace\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r":root\s*\{[^}]*--workspace-side-action-width:\s*164px")
        self.assertRegex(styles, r"\.image-input-workspace\s*\{[^}]*--quick-gallery-column-width:\s*var\(--workspace-side-action-width\)")
        self.assertRegex(styles, r"\.image-input-workspace\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+var\(--quick-gallery-column-width\)")
        self.assertRegex(styles, r"\.image-input-workspace\s*\{[^}]*--image-input-action-height:\s*40px")
        self.assertRegex(styles, r"\.image-input-workspace\s*\{[^}]*--image-input-thumb-size:\s*116px")
        self.assertRegex(styles, r"\.image-input-workspace\s*\{[^}]*--quick-gallery-height:\s*var\(--image-input-main-height\)")
        self.assertRegex(styles, r"@container\s+workspace\s*\(max-width:\s*520px\)\s*\{[\s\S]*\.image-input-workspace[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertNotIn("@container (max-width: 620px)", styles)
        self.assertRegex(styles, r"\.image-input-main\s*\{[^}]*border:\s*1px dashed color-mix\(in srgb, var\(--text-secondary\) 36%, var\(--line\)\)")
        self.assertRegex(styles, r"\.image-input-main\s*\{[^}]*height:\s*var\(--image-input-main-height\)")
        self.assertRegex(styles, r"\.image-input-left\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.image-input-left\s*\{[^}]*flex-direction:\s*column")
        self.assertRegex(styles, r"\.image-input-left\s*\{[^}]*height:\s*var\(--image-input-total-height\)")
        self.assertRegex(styles, r"\.image-input-footer\s*\{[^}]*grid-template-columns:\s*auto minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.image-input-footer\s*\{[^}]*height:\s*var\(--image-input-action-height\)")
        self.assertRegex(styles, r"\.image-input-actions\s*\{[^}]*justify-content:\s*flex-start")
        self.assertRegex(styles, r"\.image-input-actions\s*\{[^}]*height:\s*var\(--image-input-action-height\)")
        self.assertRegex(styles, r"\.image-input-actions\s*\{[^}]*flex-wrap:\s*nowrap")
        self.assertRegex(styles, r"\.image-input-actions\s+\.ghost-button\s*,\s*\.gallery-manage-panel\s+\.resource-manage-button\s*\{[^}]*height:\s*var\(--image-input-action-height\)")
        self.assertRegex(styles, r"\.image-gallery-column\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.image-gallery-column\s*\{[^}]*grid-template-rows:\s*var\(--quick-gallery-height\)\s+var\(--image-input-action-height\)")
        self.assertRegex(styles, r"\.image-uploader-grid\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.image-uploader-grid\s*\{[^}]*height:\s*100%")
        self.assertRegex(styles, r"\.image-uploader-grid\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.image-strip\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.image-strip\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.image-uploader-grid\.has-inputs\s+\.image-strip\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+var\(--image-upload-source-compact-width\)")
        self.assertRegex(styles, r"\.image-thumb-list\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.image-uploader-grid\.has-inputs\s+\.image-thumb-list\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.image-thumb-list\s*\{[^}]*overflow-x:\s*auto")
        self.assertRegex(styles, r"\.image-upload-source\s*\{[^}]*height:\s*100%")
        self.assertRegex(styles, r"\.thumb\s*\{[^}]*width:\s*var\(--image-input-thumb-size\)")
        self.assertRegex(styles, r"\.thumb\s*\{[^}]*height:\s*var\(--image-input-thumb-size\)")
        self.assertNotRegex(styles, r"\.image-upload-source\s*\{[^}]*flex:\s*1 0 220px")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.image-strip\s*\{[^}]*grid-template-rows:\s*var\(--image-input-compact-thumb-size\)")
        self.assertNotRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.image-strip\s*\{[^}]*grid-template-rows:\s*repeat\(2,")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.image-strip\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+var\(--image-input-compact-thumb-size\)")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.image-strip\s*\{[^}]*gap:\s*6px")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.image-strip\s*\{[^}]*overflow:\s*hidden")
        self.assertNotRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.image-strip\s*\{[^}]*overflow-x:\s*auto")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s*\{[^}]*padding:\s*8px")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.image-thumb-list\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.thumb\s*,\s*\.image-uploader-grid\.compact-grid\s+\.image-upload-source\s*\{[^}]*width:\s*var\(--image-input-compact-thumb-size\)")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.thumb-badge\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.thumb\s+\.thumb-remove\s*\{[^}]*width:\s*16px")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.add-upload-to-gallery\s*\{[^}]*width:\s*20px")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.add-upload-to-gallery\s+\.thumb-add-icon\s*\{[^}]*width:\s*16px")
        self.assertNotIn("@container (max-width: 540px)", styles)
        self.assertRegex(styles, r"\.upload-title-compact\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.image-uploader-grid\.has-inputs\s+\.upload-title-full\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.image-uploader-grid\.has-inputs\s+\.upload-title-compact\s*\{[^}]*display:\s*inline")
        self.assertIn("const compactGrid = imageStripNeedsCompactGrid();", script)
        self.assertIn("const thumbCount = state.images.length + state.referenceFiles.length;", script)
        self.assertIn("const thumbItems = els.imageThumbItems;", script)
        self.assertNotIn("els.imageThumbItems || els.imageThumbList", script)
        self.assertNotIn('els.imageThumbList.innerHTML = ""', script)
        self.assertIn("function handleImageStripWheel", script)
        self.assertIn('els.imageStrip?.addEventListener("wheel", handleImageStripWheel, { passive: false })', script)
        self.assertIn("const nextScrollLeft = Math.min(maxScrollLeft, Math.max(0, scrollTarget.scrollLeft + wheelDelta));", script)
        self.assertIn("event.preventDefault();", script)
        self.assertNotIn("state.images.length >= 4 || imageStripNeedsCompactGrid()", script)
        self.assertRegex(script, r"els\.imageUploaderGrid\?\.classList\.toggle\(\"has-images\",\s*hasImages\)")
        self.assertRegex(script, r"els\.imageUploaderGrid\?\.classList\.toggle\(\"has-inputs\",\s*hasInputs\)")
        self.assertRegex(script, r"els\.imageUploaderGrid\?\.classList\.toggle\(\"compact-grid\",\s*compactGrid\)")
        self.assertRegex(styles, r"\.upload-tile\s*\{[^}]*height:\s*100%")
        self.assertRegex(styles, r"\.upload-tile\s*\{[^}]*border:\s*none")
        self.assertRegex(styles, r"\.quick-gallery-dock\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.quick-gallery-dock\s*\{[^}]*height:\s*var\(--quick-gallery-height\)")
        self.assertRegex(styles, r"\.quick-gallery-picker\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+52px")
        self.assertRegex(styles, r"\.quick-gallery-rail\s*\{[^}]*height:\s*100%")
        self.assertRegex(styles, r"\.quick-gallery-rail\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.quick-gallery-rail\s*\{[^}]*flex-direction:\s*column")
        self.assertRegex(styles, r"\.quick-gallery-rail\s*\{[^}]*overflow-y:\s*auto")
        self.assertRegex(styles, r"\.quick-gallery-rail\s*\{[^}]*scroll-snap-type:\s*y proximity")
        self.assertRegex(styles, r"\.quick-gallery-rail\s*\{[^}]*scrollbar-width:\s*none")
        self.assertRegex(styles, r"\.quick-gallery-rail::\-webkit-scrollbar\s*\{[^}]*display:\s*none")
        self.assertNotRegex(styles, r"\.quick-gallery-rail\s*\{[^}]*grid-template-rows:\s*repeat\(3,\s*1fr\)")
        self.assertRegex(styles, r"\.quick-gallery-category\s*\{[^}]*flex:\s*0 0 30px")
        self.assertRegex(styles, r"\.quick-gallery-category\s*\{[^}]*height:\s*30px")
        self.assertRegex(styles, r"\.quick-gallery-category\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.quick-gallery-category\s*\{[^}]*text-overflow:\s*ellipsis")
        self.assertRegex(styles, r"\.quick-gallery-category\s*\{[^}]*white-space:\s*nowrap")
        self.assertRegex(styles, r"\.quick-gallery-category\s*\{[^}]*scroll-snap-align:\s*start")
        self.assertRegex(styles, r"\.quick-gallery-preview\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.quick-gallery-preview\s*\{[^}]*top:\s*50%")
        self.assertRegex(styles, r"\.quick-gallery-preview\s*\{[^}]*pointer-events:\s*none")
        self.assertRegex(styles, r"\.quick-gallery-preview\s*\{[^}]*opacity:\s*0")
        self.assertRegex(styles, r"\.quick-gallery-preview\.visible\s*\{[^}]*opacity:\s*1")
        self.assertRegex(styles, r"\.quick-gallery-list\s*\{[^}]*overflow-y:\s*auto")
        self.assertRegex(styles, r"\.quick-gallery-list\s*\{[^}]*--quick-gallery-item-height:\s*30px")
        self.assertNotIn("--quick-gallery-center-pad", styles)
        self.assertRegex(styles, r"\.quick-gallery-list\s*\{[^}]*padding:\s*0\s+4px\s+0\s+0")
        self.assertRegex(styles, r"\.quick-gallery-list\s*\{[^}]*scroll-snap-type:\s*y proximity")
        self.assertNotRegex(styles, r"\.quick-gallery-list\s*\{[^}]*scroll-padding-block:")
        self.assertRegex(styles, r"\.quick-gallery-list\s*\{[^}]*scrollbar-width:\s*none")
        self.assertRegex(styles, r"\.quick-gallery-list::\-webkit-scrollbar\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.quick-gallery-item\s*\{[^}]*text-align:\s*center")
        self.assertRegex(styles, r"\.quick-gallery-item\s*\{[^}]*cursor:\s*pointer")
        self.assertRegex(styles, r"\.quick-gallery-item\s*\{[^}]*scroll-snap-align:\s*start")
        self.assertRegex(styles, r"\.quick-gallery-item\.near\s*\{[^}]*opacity:")
        self.assertRegex(styles, r"\.quick-gallery-item\.center\s*\{[^}]*box-shadow:")
        self.assertRegex(styles, r"\.quick-gallery-item\.center\.active\s*\{[^}]*box-shadow:")
        self.assertRegex(styles, r"\.quick-gallery-list\.bounce-top\s*\{[^}]*animation:\s*quickGalleryBounceTop")
        self.assertRegex(styles, r"\.quick-gallery-list\.bounce-bottom\s*\{[^}]*animation:\s*quickGalleryBounceBottom")
        self.assertIn("@keyframes quickGalleryBounceTop", styles)
        self.assertIn("@keyframes quickGalleryBounceBottom", styles)
        self.assertIn("@media (prefers-reduced-motion: reduce)", styles)
        self.assertRegex(styles, r"\.gallery-fly-clone\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.gallery-manage-panel\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.gallery-manage-panel\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.gallery-manage-panel\s*\{[^}]*justify-content:\s*flex-end")
        self.assertNotRegex(styles, r"\.gallery-manage-panel\s*\{[^}]*border:")
        self.assertRegex(styles, r"\.gallery-manage-panel\s+\.resource-manage-button\s*\{[^}]*flex:\s*1 1 auto")
        resource_button_styles = self._extract_css_block(styles, ".resource-manage-button")
        self.assertIn("width: 100%", resource_button_styles)
        self.assertIn("background: var(--primary)", resource_button_styles)
        self.assertIn("border-color: var(--primary)", resource_button_styles)
        self.assertIn("color: var(--primary-foreground)", resource_button_styles)
        self.assertNotIn("thumb-label", script)
        self.assertNotIn(".thumb-label", styles)

    def test_short_desktop_recent_uploads_fit_inside_reference_input_footer(self) -> None:
        responsive = Path(
            "codex_image/webui/static/styles/80-utilities-responsive.css"
        ).read_text(encoding="utf-8")
        compact = self._extract_css_at_rule(
            responsive,
            "@media (max-height: 1390px) and (min-width: 900px)",
        )

        self.assertRegex(
            compact,
            r"\.image-input-workspace\s*\{[^}]*--recent-asset-size:\s*"
            r"clamp\(\s*24px,\s*calc\(var\(--image-input-action-height\)\s*-\s*4px\),\s*32px\s*\)",
        )

    def test_very_short_desktop_uses_continuous_summary_height(self) -> None:
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")
        output = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")
        lock_source = Path("codex_image/webui/frontend/src/output-settings-lock.ts").read_text(encoding="utf-8")

        self.assertNotIn("@media (max-height: 820px)", responsive)
        self.assertRegex(
            responsive,
            r"\.controls-col\s+\.image-panel\s*\{[^}]*"
            r"flex:\s*1\s+0\s+auto",
        )
        self.assertRegex(output, r"\.output-settings-locked-summary\s*\{[^}]*position:\s*absolute[^}]*inset:\s*0")
        self.assertNotIn("--output-settings-editor-height", responsive + output + lock_source)
        self.assertNotIn("getBoundingClientRect", lock_source)

    def test_mid_width_short_desktop_keeps_input_gallery_side_rail_aligned(self) -> None:
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")
        compact = self._extract_last_css_at_rule(responsive, "@container workspace (max-width: 1100px)")

        self.assertRegex(compact, r"\.dashboard\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.1fr\)\s+minmax\(320px,\s*0\.9fr\)")
        self.assertRegex(compact, r"\.controls-col\s+\.image-input-workspace\s*\{[^}]*--quick-gallery-column-width:\s*132px")
        self.assertRegex(compact, r"\.controls-col\s+\.image-input-workspace\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+var\(--quick-gallery-column-width\)")
        self.assertNotRegex(compact, r"height:\s*var\(--(?:image-input-total|quick-gallery)-height\)")
        self.assertRegex(compact, r"\.controls-col\s+\.prompt-panel\s*\{[^}]*--prompt-action-column-width:\s*132px")
    def test_gallery_categories_are_managed_from_server_in_management_sheet(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="galleryDrawer"', html)
        self.assertIn('id="galleryDrawerBackdrop"', html)
        self.assertNotIn('id="galleryModal"', html)
        self.assertIn('class="resource-sheet resource-sheet-wide gallery-drawer"', html)
        self.assertIn('id="galleryDrawerCategoryTabs"', html)
        self.assertIn('id="galleryCategoryManageToggle"', html)
        self.assertIn('id="galleryCategoryManagePanel"', html)
        self.assertIn('id="galleryCategoryList"', html)
        self.assertIn('id="addGalleryCategoryButton"', html)
        self.assertNotIn('id="galleryModalCategoryRail"', html)
        self.assertNotIn('class="gallery-category-view-row"', html)
        self.assertNotIn("查看分类</span>", html)
        self.assertIn("galleryCategories: defaultGalleryCategories()", script)
        self.assertIn("galleryDrawer: document.querySelector", script)
        self.assertIn("galleryDrawerBackdrop: document.querySelector", script)
        self.assertIn("galleryDrawerCategoryTabs: document.querySelector", script)
        self.assertIn("galleryCategoryManageToggle: document.querySelector", script)
        self.assertIn("galleryCategoryManagePanel: document.querySelector", script)
        self.assertNotIn("galleryModalCategoryRail: document.querySelector", script)
        self.assertIn("galleryCategoryList: document.querySelector", script)
        self.assertIn("addGalleryCategoryButton: document.querySelector", script)
        self.assertIn('fetch("/api/gallery/categories"', script)
        self.assertIn("function renderGalleryCategoryControls()", script)
        self.assertIn("function renderGalleryDrawerCategoryTabs()", script)
        self.assertIn("function handleGalleryDrawerCategoryTabClick(event)", script)
        self.assertIn("function toggleGalleryCategoryManager()", script)
        self.assertNotIn("function handleGalleryModalCategoryEvent(event)", script)
        self.assertIn("function setGalleryDrawerCategory(category)", script)
        self.assertIn("function handleGalleryCategoryListClick(event)", script)
        self.assertIn('els.galleryCategoryList?.addEventListener("click", handleGalleryCategoryListClick)', script)
        self.assertIn('els.galleryDrawerCategoryTabs?.addEventListener("click", handleGalleryDrawerCategoryTabClick)', script)
        self.assertIn('event.target.closest?.("[data-gallery-category-save],[data-gallery-category-delete]")', script)
        self.assertIn("updateGalleryCategory(button.dataset.galleryCategorySave)", script)
        self.assertIn("deleteGalleryCategory(button, button.dataset.galleryCategoryDelete)", script)
        self.assertIn('fetch("/api/gallery/categories/reorder"', script)
        self.assertIn("handleGalleryCategoryDragStart", script)
        self.assertIn("handleGalleryCategoryDragOver", script)
        self.assertIn("handleGalleryCategoryDrop", script)
        self.assertIn("handleGalleryCategoryDragEnd", script)
        self.assertIn("function createGalleryDragPreview", script)
        self.assertIn("function createGalleryElementDragPreview", script)
        self.assertIn("function setGalleryDragPreview", script)
        self.assertIn('els.galleryCategoryList?.addEventListener("dragstart", handleGalleryCategoryDragStart)', script)
        self.assertIn('els.galleryCategoryList?.addEventListener("dragover", handleGalleryCategoryDragOver)', script)
        self.assertIn('els.galleryCategoryList?.addEventListener("drop", handleGalleryCategoryDrop)', script)
        self.assertIn('data-gallery-category-drag-handle', script)
        self.assertIn("function renderGalleryGridWithHeightTransition()", script)
        self.assertIn("function shouldAnimateGalleryGridHeight()", script)
        self.assertIn("function resetGalleryGridTransition", script)
        self.assertIn("function activeGalleryGridLayer()", script)
        self.assertIn("function galleryGridLayerHtml(items)", script)
        self.assertIn("function bindGalleryGridActions", script)
        self.assertIn('fetch("/api/gallery/reorder"', script)
        self.assertIn("handleGalleryGridDragStart", script)
        self.assertIn("handleGalleryGridDragOver", script)
        self.assertIn("handleGalleryGridDrop", script)
        self.assertIn("handleGalleryGridDragEnd", script)
        self.assertIn("dataTransfer.setDragImage", script)
        self.assertIn("sourceElement: card", script)
        self.assertIn("sourceElement: categoryRow(categoryId)", script)
        self.assertIn("function galleryGridDomOrder()", script)
        self.assertIn("function moveGalleryGridDragPlaceholder", script)
        self.assertIn("moveGalleryGridDragPlaceholder(targetCard, placement)", script)
        self.assertIn("function categoryDomOrder()", script)
        self.assertIn("function moveGalleryCategoryDragPlaceholder", script)
        self.assertIn("moveGalleryCategoryDragPlaceholder(targetRow, placement)", script)
        self.assertIn("gallery-drag-preview", script)
        self.assertIn('els.galleryGrid?.addEventListener("dragstart", handleGalleryGridDragStart)', script)
        self.assertIn('els.galleryGrid?.addEventListener("dragover", handleGalleryGridDragOver)', script)
        self.assertIn('els.galleryGrid?.addEventListener("drop", handleGalleryGridDrop)', script)
        self.assertIn("data-gallery-order-handle", script)
        self.assertIn('nextLayer.className = "gallery-grid-layer mode-transition mode-collapsed"', script)
        self.assertIn('currentLayer.classList.add("mode-collapsed")', script)
        self.assertIn('nextLayer.classList.remove("mode-collapsed")', script)
        self.assertIn("renderGalleryGrid({ animateHeight: true })", script)
        self.assertIn("function renderGalleryCategoryManager()", script)
        self.assertIn("function createGalleryCategory()", script)
        self.assertIn("function updateGalleryCategory", script)
        self.assertIn("function deleteGalleryCategory", script)
        self.assertIn("function categoryPromptRole(category)", script)
        self.assertIn('legacyMethod("closePromptTemplateDrawer", { restoreFocus: false })', script)
        self.assertIn("data-gallery-category-name", script)
        self.assertIn("data-gallery-category-prompt-role", script)
        self.assertIn("data-gallery-category-delete", script)
        self.assertIn("data-gallery-category-drag-handle", script)
        self.assertNotIn("data-gallery-category-view", script)
        self.assertNotIn("data-gallery-category-order", script)
        self.assertNotIn('querySelectorAll("[data-gallery-category-view]").forEach', script)
        self.assertNotIn("data-gallery-modal-category", script)
        self.assertNotIn("GALLERY_CATEGORY_LABEL_STORAGE_KEY", script)
        self.assertNotIn("localStorage.setItem(GALLERY_CATEGORY_LABEL_STORAGE_KEY", script)
        self.assertRegex(styles, r"\.resource-sheet\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.resource-sheet-wide\s*\{[^}]*width:\s*min\(760px,\s*52vw\)")
        self.assertIn(".gallery-drawer-top", styles)
        self.assertIn(".gallery-drawer-category-tabs", styles)
        self.assertRegex(styles, r"\.gallery-drawer-body\s*\{[^}]*grid-template-columns:\s*1fr[^}]*grid-template-rows:\s*auto\s+minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.gallery-drawer-category-tabs\s+\.quick-gallery-category\s*\{[^}]*width:\s*auto")
        self.assertRegex(styles, r"\.gallery-drawer-category-tabs\s+\.quick-gallery-category\s*\{[^}]*flex:\s*0\s+0\s+auto")
        self.assertRegex(styles, r"\.gallery-category-manage-panel\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.gallery-category-manage-panel\s*\{[^}]*width:\s*100%")
        self.assertNotIn(".gallery-category-order", styles)
        self.assertNotRegex(styles, r"\.gallery-category-view-row\s*\{")
        self.assertNotRegex(styles, r"\.gallery-modal-category-rail\s*\{")
        self.assertNotRegex(styles, r"\.gallery-modal-category\.active\s*\{")
        self.assertIn(".gallery-drag-handle", styles)
        self.assertRegex(styles, r"\.gallery-drag-handle\s*\{[^}]*cursor:\s*grab")
        self.assertIn(".gallery-drag-preview", styles)
        self.assertIn(".gallery-drag-preview-clone", styles)
        self.assertNotIn("gallery-category-current-badge", script)
        self.assertNotIn("gallery-category-current-placeholder", script)
        self.assertIn("aria-current=", script)
        self.assertIn("gallery-card-drag-strip", script)
        self.assertRegex(styles, r"\.gallery-category-create-row\s*\{[^}]*grid-template-columns:\s*34px\s+minmax\(160px,\s*1fr\)\s+minmax\(220px,\s*1\.5fr\)\s+auto")
        self.assertRegex(styles, r"\.gallery-category-row\s*\{[^}]*grid-template-columns:\s*34px\s+minmax\(160px,\s*1fr\)\s+minmax\(220px,\s*1\.5fr\)\s+auto")
        self.assertRegex(styles, r"\.gallery-category-row-toolbar\s*\{[^}]*width:\s*34px")
        self.assertIn(".gallery-category-row.is-current", styles)
        self.assertRegex(styles, r"\.gallery-card\s*\{[^}]*grid-template-rows:\s*auto\s+auto\s+auto\s+auto")
        self.assertRegex(styles, r"\.gallery-card-drag-strip\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.gallery-card-drag-strip\s*\{[^}]*cursor:\s*grab")
        self.assertIn(".gallery-card-heading", styles)
        self.assertNotRegex(styles, r"\.gallery-card-drag-handle\s*\{[^}]*position:\s*absolute")
        self.assertIn(".gallery-category-row.drop-target", styles)
        self.assertIn(".gallery-card.drop-target", styles)
        self.assertRegex(styles, r"\.gallery-category-row\.is-dragging,\s*\.gallery-card\.is-dragging\s*\{[^}]*opacity:\s*0\.42[^}]*\}")
        self.assertRegex(styles, r"\.gallery-grid\s*\{[^}]*transition:\s*height var\(--motion-height\)")
        self.assertRegex(styles, r"\.gallery-grid\.is-transitioning\s*\{[^}]*will-change:\s*height")
        self.assertRegex(styles, r"\.gallery-grid\s*>\s*\.gallery-grid-layer\s*\{[^}]*grid-area:\s*1\s*/\s*1")
        self.assertRegex(styles, r"\.gallery-grid-layer\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.gallery-grid-layer\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fill,\s*minmax\(min\(100%,\s*220px\),\s*1fr\)\)")
        self.assertRegex(styles, r"\.gallery-card\s*\{[^}]*container-type:\s*inline-size")
        self.assertRegex(styles, r"\.gallery-card\s*\{[^}]*min-width:\s*0")
        self.assertRegex(styles, r"\.gallery-card\s*\{[^}]*max-width:\s*100%")
        self.assertRegex(styles, r"\.gallery-card-body\s*\{[^}]*min-width:\s*0")
        self.assertRegex(styles, r"\.gallery-card-heading\s*\{[^}]*min-width:\s*0")
        self.assertRegex(styles, r"\.gallery-card-heading strong\s*\{[^}]*display:\s*block[^}]*min-width:\s*0")
        self.assertRegex(styles, r"\.gallery-card-body span\s*\{[^}]*min-width:\s*0[^}]*overflow:\s*hidden[^}]*text-overflow:\s*ellipsis[^}]*white-space:\s*nowrap")
        self.assertRegex(styles, r"\.gallery-card-actions\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)")
        self.assertRegex(styles, r"\.gallery-card-actions\s*\{[^}]*min-width:\s*0")
        self.assertRegex(styles, r"\.gallery-card-actions \.ghost-button\s*\{[^}]*min-width:\s*0[^}]*overflow:\s*hidden[^}]*text-overflow:\s*ellipsis[^}]*white-space:\s*nowrap")
        self.assertRegex(styles, r"@container \(max-width:\s*219px\)\s*\{[\s\S]*\.gallery-card-actions\s*\{[\s\S]*grid-template-columns:\s*1fr")
        self.assertNotIn("@keyframes galleryGridItemFadeIn", styles)
        self.assertRegex(styles, r"@media \(prefers-reduced-motion: reduce\)\s*\{[\s\S]*\.gallery-grid\s*\{[\s\S]*transition:\s*none")
        self.assertRegex(styles, r"\.gallery-category-list\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.gallery-category-row\s*\{[^}]*display:\s*grid")
        self.assertIn(".gallery-category-row-toolbar", styles)
        self.assertIn(".gallery-category-row-actions", styles)
        self.assertRegex(styles, r"@media \(max-width:\s*640px\)\s*\{[\s\S]*\.gallery-category-manage-panel\s*\{[\s\S]*grid-template-columns:\s*1fr")
        self.assertRegex(styles, r"@media \(max-width:\s*640px\)\s*\{[\s\S]*\.gallery-category-create-row\s*\{[\s\S]*grid-template-columns:\s*1fr")
        self.assertRegex(styles, r"@media \(max-width:\s*640px\)\s*\{[\s\S]*\.gallery-category-row\s*\{[\s\S]*grid-template-areas:")
    def test_gallery_item_edits_use_inline_popover(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotIn("window.prompt", script)
        self.assertIn("function openGalleryEditPopover", script)
        self.assertIn("function closeGalleryEditPopover", script)
        self.assertIn("closeConfirmPopover,", script)
        self.assertIn("positionGalleryEditPopover(anchor, popover)", script)
        self.assertIn("renameGalleryItem(button", script)
        self.assertIn("moveGalleryItem(button", script)
        self.assertIn("function handleGalleryGridClick(event)", script)
        self.assertIn('els.galleryGrid?.addEventListener("click", handleGalleryGridClick)', script)
        self.assertIn('event.target.closest?.("[data-gallery-use],[data-gallery-rename],[data-gallery-replace],[data-gallery-move],[data-gallery-note],[data-gallery-delete]")', script)
        self.assertIn("data-gallery-edit-save", script)
        self.assertIn("data-gallery-edit-cancel", script)
        self.assertIn("data-gallery-edit-name", script)
        self.assertIn("data-gallery-edit-category", script)
        self.assertIn("data-gallery-replace", script)
        self.assertRegex(script, r'data-gallery-use="\$\{escapeHtml\(item\.id\)\}">\$\{translate\("gallery\.use"\)\}</button>')
        self.assertRegex(script, r'data-gallery-replace="\$\{escapeHtml\(item\.id\)\}">\$\{translate\("gallery\.replace"\)\}</button>')
        self.assertNotIn(">替换图像</button>", script)
        self.assertIn("function replaceGalleryItemImage", script)
        self.assertIn('fetch(`/api/gallery/${encodeURIComponent(itemId)}/image`', script)
        self.assertNotIn('querySelectorAll("[data-gallery-rename]").forEach', script)
        self.assertRegex(styles, r"\.gallery-edit-popover\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.gallery-edit-field\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.gallery-edit-actions\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.gallery-card-actions\s*\{[^}]*grid-template-columns")
        self.assertNotRegex(styles, r"\.gallery-card-actions\s+\[data-gallery-replace\]\s*\{[^}]*grid-column")
    def test_model_provider_selector_replaces_auth_source_switcher_in_top_nav(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        auth_source = Path("codex_image/webui/frontend/src/auth-source.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        nav_actions = html[html.index('<div class="nav-actions">'):html.index('<div id="taskNotificationCenter"')]
        self.assertNotIn('id="authSourceGroup"', nav_actions)
        self.assertNotIn('data-auth-source="codex"', nav_actions)
        self.assertNotIn('data-auth-source="api"', nav_actions)
        self.assertIn('id="generationProviderSelect"', nav_actions)
        self.assertIn('id="generationProviderSettingsButton"', nav_actions)
        self.assertIn('generationProviderSelect: document.querySelector', script)
        self.assertIn('return state.selectedProviderId === "codex" ? "codex" : "api";', auth_source)
        self.assertRegex(styles, r"\.generation-provider-control\s*\{[^}]*min-width:\s*0")
        self.assertRegex(
            styles,
            r"\.generation-provider-select-shell\s+\.themed-select-trigger\s*\{[^}]*text-overflow:\s*ellipsis",
        )

    def test_output_and_auth_switchers_use_sliding_segmented_indicator(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        indicator_source = Path("codex_image/webui/frontend/src/segmented-indicator.ts").read_text(encoding="utf-8")

        self.assertIn('import { initSegmentedIndicatorFeature } from "./segmented-indicator";', main_source)
        self.assertLess(main_source.index("initSegmentedIndicatorFeature();"), main_source.index("window.__codexImageWebUI?.boot();"))
        self.assertIn(
            '".radio-group:not(.ratio-group):not(.model-parameter-segmented-multiline):not(.model-aspect-ratio-grid)"',
            indicator_source,
        )
        self.assertIn('"#authSourceGroup"', indicator_source)
        self.assertIn('"#systemSettingsTabs"', indicator_source)
        self.assertIn(".system-settings-tab", indicator_source)
        self.assertIn("refreshSegmentedIndicators", indicator_source)
        self.assertIn("getBoundingClientRect()", indicator_source)
        self.assertIn("window.getComputedStyle(host)", indicator_source)
        self.assertIn("borderLeftWidth", indicator_source)
        self.assertIn("borderTopWidth", indicator_source)
        self.assertIn("activeRect.left - hostRect.left - borderLeft", indicator_source)
        self.assertIn("activeRect.top - hostRect.top - borderTop", indicator_source)
        self.assertIn("--segmented-indicator-x", indicator_source)
        self.assertIn("--segmented-indicator-width", indicator_source)
        self.assertIn("MutationObserver", indicator_source)
        self.assertIn("ResizeObserver", indicator_source)

        self.assertRegex(styles, r"\.segmented-indicator-host\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.segmented-indicator-host\s*\{[^}]*isolation:\s*isolate")
        self.assertRegex(styles, r"\.radio-group\s*\{[^}]*--segmented-control-padding:\s*3px")
        self.assertRegex(styles, r"\.radio-group\s*\{[^}]*--segmented-control-height:\s*30px")
        self.assertRegex(styles, r"\.radio-group\s*\{[^}]*align-items:\s*stretch")
        self.assertRegex(styles, r"\.radio-group\s*\{[^}]*padding:\s*var\(--segmented-control-padding\)")
        self.assertRegex(styles, r"\.radio-btn\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.radio-btn\s*\{[^}]*align-items:\s*center")
        self.assertRegex(styles, r"\.radio-btn\s*\{[^}]*height:\s*var\(--segmented-control-height\)")
        self.assertRegex(styles, r"\.radio-btn\s*\{[^}]*border-radius:\s*var\(--segmented-indicator-radius\)")
        self.assertRegex(styles, r"\.ratio-group\s+\.radio-btn\s*\{[^}]*height:\s*100%")
        self.assertRegex(styles, r"\.segmented-indicator\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.segmented-indicator\s*\{[^}]*border-radius:\s*var\(--segmented-indicator-radius\)")
        self.assertRegex(styles, r"\.segmented-indicator\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.segmented-indicator\s*\{[^}]*transform:\s*translate3d\(var\(--segmented-indicator-x")
        self.assertRegex(styles, r"\.segmented-indicator\s*\{[^}]*transition:\s*none")
        indicator_transition = styles.split(
            ".segmented-indicator-host.segmented-indicator-ready .segmented-indicator {", 1
        )[1].split("}", 1)[0]
        self.assertIn("transform var(--motion-base)", indicator_transition)
        self.assertIn("opacity var(--motion-fast)", indicator_transition)
        self.assertNotIn("width var(", indicator_transition)
        self.assertNotIn("height var(", indicator_transition)
        self.assertRegex(styles, r"\.radio-group\.segmented-indicator-host\s+\.radio-btn\.active\s*\{[^}]*background:\s*transparent")
        self.assertRegex(styles, r"\.system-settings-tabs\.segmented-indicator-host\s+\.system-settings-tab\.active\s*\{[^}]*background:\s*transparent")
        self.assertRegex(styles, r"\.system-settings-tabs\.segmented-indicator-host\s+\.system-settings-tab\.active\s*\{[^}]*color:\s*var\(--primary-foreground\)")
        self.assertRegex(styles, r"@media \(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*\.segmented-indicator\s*\{[^}]*transition:\s*none")
    def test_system_settings_restores_focus_before_hiding_modal(self) -> None:
        source = Path("codex_image/webui/frontend/src/system-settings.ts").read_text(encoding="utf-8")

        self.assertIn("let systemSettingsReturnFocus: HTMLElement | null = null", source)
        self.assertIn("systemSettingsReturnFocus = activeElement", source)
        self.assertIn("modal.contains(activeElement)", source)
        self.assertIn("returnFocus.focus({ preventScroll: true })", source)
        self.assertLess(
            source.index("returnFocus.focus({ preventScroll: true })"),
            source.index('modal?.setAttribute("aria-hidden", "true")'),
        )

    def test_provider_settings_and_system_settings_modal_contract(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        event_source = Path("codex_image/webui/frontend/src/event-bindings.ts").read_text(encoding="utf-8")
        advanced_source = Path("codex_image/webui/frontend/src/api-advanced-settings.ts").read_text(encoding="utf-8")
        provider_list_source = Path("codex_image/webui/frontend/src/api-provider-list-ui.ts").read_text(encoding="utf-8")
        provider_source = Path("codex_image/webui/frontend/src/api-provider-settings.ts").read_text(encoding="utf-8")
        provider_sort_source = Path("codex_image/webui/frontend/src/api-provider-sort.ts").read_text(encoding="utf-8")
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotIn('data-auth-source="api"', html)
        self.assertIn('id="generationProviderSelect"', html)
        self.assertNotIn('onclick="setAuthSource', html)
        self.assertIn('id="systemSettingsModal"', html)
        self.assertIn('id="systemSettingsTabs"', html)
        self.assertNotIn('data-i18n="systemSettings.subtitle"', html)
        self.assertNotIn('data-i18n="apiSettings.title"', html)
        self.assertNotIn('data-i18n="codexSettings.title"', html)
        self.assertNotIn('data-i18n="settings.title"', html)
        self.assertNotIn('class="system-settings-section-heading"', html)
        self.assertIn('id="systemSettingsApiTab"', html)
        self.assertIn('id="systemSettingsLanguageTab"', html)
        self.assertIn('id="systemSettingsStorageTab"', html)
        self.assertIn('id="systemSettingsApiPanel"', html)
        self.assertIn('id="systemSettingsLanguagePanel"', html)
        self.assertIn('id="systemSettingsStoragePanel"', html)
        self.assertIn('id="languageSelect"', html)
        self.assertIn('id="apiSettingsStatus"', html)
        self.assertNotIn('id="codexSettingsStatus"', html)
        self.assertIn('id="languageSettingsStatus"', html)
        self.assertIn('id="settingsStatus"', html)
        self.assertIn('class="api-settings-feedback settings-action-status"', html)
        self.assertIn('class="settings-action-status" data-i18n="settings.status"', html)
        self.assertIn('class="settings-action-status language-settings-status" data-i18n="languageSettings.instantStatus"', html)
        self.assertNotIn('id="apiSettingsStatus" class="api-settings-feedback" data-i18n="apiSettings.status"', html)
        self.assertIn("let systemSettingsBackdropPointerDown = false", event_source)
        self.assertIn('systemSettingsModal?.addEventListener("pointerdown"', event_source)
        self.assertIn("systemSettingsBackdropPointerDown = event.target === els.systemSettingsModal", event_source)
        self.assertIn("if (event.target === els.systemSettingsModal && systemSettingsBackdropPointerDown)", event_source)
        self.assertNotIn('if (event.target === els.systemSettingsModal) call(methods, "closeSystemSettingsModal")', event_source)
        self.assertLess(html.index('id="systemSettingsApiTab"'), html.index('id="systemSettingsLanguageTab"'))
        self.assertLess(html.index('id="systemSettingsLanguageTab"'), html.index('id="systemSettingsStorageTab"'))
        self.assertLess(html.index('id="systemSettingsApiPanel"'), html.index('id="systemSettingsLanguagePanel"'))
        self.assertLess(html.index('id="systemSettingsLanguagePanel"'), html.index('id="systemSettingsStoragePanel"'))
        self.assertIn('aria-selected="true"', html)
        self.assertIn('data-system-settings-tab="api"', html)
        self.assertNotIn('data-system-settings-tab="codex"', html)
        self.assertIn('data-system-settings-tab="language"', html)
        self.assertIn('data-system-settings-tab="storage"', html)
        self.assertIn('id="apiBaseUrl"', html)
        self.assertNotIn('id="apiRequestEndpointPreview"', html)
        self.assertIn('id="providerBindingsCount"', html)
        provider_name_field_start = html.index('class="field api-provider-name-field"')
        provider_icon_input_start = html.index('id="apiProviderIconEmoji"')
        provider_name_input_start = html.index('id="apiProviderName"')
        base_url_field_start = html.index('class="field api-base-url-field"')
        api_key_field_start = html.index('class="field api-key-field"')
        concurrency_field_start = html.index('class="field api-concurrency-field"')
        bindings_editor_start = html.index('class="provider-bindings-editor"')
        self.assertNotIn('class="field api-provider-icon-field"', html)
        self.assertLess(provider_name_field_start, provider_icon_input_start)
        self.assertLess(provider_icon_input_start, provider_name_input_start)
        self.assertLess(provider_name_field_start, base_url_field_start)
        self.assertLess(base_url_field_start, api_key_field_start)
        self.assertLess(provider_name_input_start, concurrency_field_start)
        self.assertLess(concurrency_field_start, base_url_field_start)
        self.assertLess(concurrency_field_start, bindings_editor_start)
        self.assertIn('id="apiKey"', html)
        self.assertNotIn('id="apiAuthScheme"', html)
        self.assertIn('id="apiImagesConcurrency"', html)
        self.assertIn('max="32"', html)
        self.assertIn('data-i18n="apiSettings.concurrency">并发上限</span>', html)
        self.assertIn('id="apiProviderBindings"', html)
        self.assertIn('id="addProviderBindingButton"', html)
        self.assertNotIn('id="saveApiSettingsButton"', html)
        self.assertNotIn('id="saveCodexSettingsButton"', html)
        self.assertIn('class="settings-modal-actions settings-status-only"', html)
        self.assertNotIn('id="apiMode"', html)
        self.assertIn('id="generationProviderSettingsButton"', html)
        self.assertNotIn('id="apiDirectSettingsButton"', html)
        self.assertIn('class="model-tool-row"', html)
        # Web search is a catalog parameter (tools.web_search), not a fixed field.
        self.assertNotIn('id="webSearchField"', html)
        self.assertIn('id="apiProvider"', html)
        self.assertIn('id="apiProviderCount"', html)
        self.assertIn('id="apiProviderSearchField"', html)
        self.assertIn('id="apiProviderSearch"', html)
        self.assertIn('data-i18n-attr="placeholder:apiSettings.searchProviders;aria-label:apiSettings.searchProviders"', html)
        self.assertIn('id="apiProviderList"', html)
        self.assertIn('id="apiProviderSection"', html)
        self.assertIn('id="apiProviderDetail"', html)
        self.assertIn('id="apiProviderDetailName"', html)
        self.assertNotIn('id="apiProviderDetailMeta"', html)
        self.assertIn('id="apiProviderDetailBaseUrl"', html)
        self.assertIn('id="apiProviderDetailKey"', html)
        self.assertIn('id="apiProviderEditor"', html)
        self.assertIn('id="apiProviderName"', html)
        self.assertIn('class="api-key-input-wrap"', html)
        api_key_match = re.search(r'<input\b[^>]*\bid="apiKey"[^>]*>', html)
        self.assertIsNotNone(api_key_match)
        api_key_input = api_key_match.group(0)
        self.assertIn('type="password"', api_key_input)
        self.assertIn('autocomplete="new-password"', api_key_input)
        self.assertIn('name="provider-api-key"', api_key_input)
        self.assertIn('autocapitalize="off"', api_key_input)
        self.assertIn('spellcheck="false"', api_key_input)
        self.assertIn('id="apiKeyRevealButton"', html)
        self.assertIn('aria-pressed="false"', html)
        self.assertIn('data-i18n-attr="aria-label:apiSettings.showApiKey;title:apiSettings.showApiKey"', html)
        self.assertIn('id="editApiProviderButton"', html)
        self.assertIn('id="copyApiProviderButton"', html)
        self.assertIn('id="addApiProviderButton"', html)
        self.assertIn('id="sortApiProvidersButton"', html)
        self.assertIn('class="api-provider-choice-grid"', html)
        self.assertIn('class="api-provider-add-button"', html)
        self.assertIn('data-i18n="apiSettings.newProviderAction"', html)
        self.assertIn('data-i18n="apiSettings.copyProvider"', html)
        self.assertIn('data-i18n="apiSettings.sortProviders"', html)
        self.assertIn('id="deleteApiProviderButton"', html)
        self.assertIn('id="cancelApiProviderEditButton"', html)
        self.assertIn('id="saveApiProviderEditButton"', html)
        self.assertIn('id="apiSettingsActions"', html)
        self.assertLess(html.index('id="apiSettingsActions"'), html.index('id="apiSettingsStatus"'))
        self.assertLess(html.index('id="languageSelect"'), html.index('id="languageSettingsStatus"'))
        self.assertLess(html.index('id="settingsStatus"'), html.index('id="saveSettingsButton"'))
        self.assertLess(html.index('id="addApiProviderButton"'), html.index('id="apiProviderList"'))
        self.assertLess(html.index('id="apiProviderDetailConcurrency"'), html.index('id="editApiProviderButton"'))
        self.assertLess(html.index('id="editApiProviderButton"'), html.index('id="copyApiProviderButton"'))
        self.assertLess(html.index('id="copyApiProviderButton"'), html.index('id="deleteApiProviderButton"'))
        self.assertLess(html.index('id="apiProviderCount"'), html.index('id="sortApiProvidersButton"'))
        self.assertLess(html.index('id="sortApiProvidersButton"'), html.index('id="apiProviderSearchField"'))
        self.assertLess(html.index('id="apiProviderSearchField"'), html.index('class="api-provider-choice-grid"'))
        self.assertLess(html.index('id="apiProviderList"'), html.index('id="apiProviderDetail"'))
        self.assertLess(html.index('id="apiProviderDetail"'), html.index('id="apiProviderEditor"'))
        self.assertIn('api-settings-feedback settings-action-status', html)
        self.assertEqual(html.count('id="mainModel"'), 1)
        self.assertNotIn('id="apiMainModel"', html)
        self.assertIn("API_SETTINGS_STORAGE_KEY", script)
        self.assertIn("systemSettingsModal: document.querySelector", script)
        self.assertIn("systemSettingsTabs: document.querySelector", script)
        self.assertNotIn("systemSettingsCodexPanel: document.querySelector", script)
        self.assertIn("systemSettingsLanguagePanel: document.querySelector", script)
        self.assertIn("languageSelect: document.querySelector", script)
        self.assertIn("function openSystemSettingsModal", script)
        self.assertIn("function setSystemSettingsTab", script)
        self.assertIn("function openSystemSettingsFromUrl", script)
        self.assertIn("new URLSearchParams(window.location.search)", script)
        self.assertIn('params.get("settings")', script)
        self.assertIn('openSystemSettingsModal(settingsTab || "api")', script)
        self.assertIn("window.history.replaceState", script)
        self.assertIn("apiBaseUrl: document.querySelector", script)
        self.assertIn("providerBindingsCount: document.querySelector", script)
        self.assertIn("apiKey: document.querySelector", script)
        self.assertIn("apiKeyRevealButton: document.querySelector", script)
        self.assertNotIn("apiAuthScheme: document.querySelector", script)
        self.assertIn("apiProviderBindings: document.querySelector", script)
        self.assertIn("addProviderBindingButton: document.querySelector", script)
        self.assertIn("apiImagesConcurrency: document.querySelector", script)
        self.assertIn("apiProviderIconEmoji: document.querySelector", script)
        self.assertNotIn("codexMode: document.querySelector", script)
        self.assertNotIn("codexModeGroup: document.querySelector", script)
        self.assertNotIn('codexModeNotes: document.querySelectorAll("[data-codex-mode-note]")', script)
        self.assertNotIn("saveApiSettingsButton: document.querySelector", script)
        self.assertNotIn("saveCodexSettingsButton: document.querySelector", script)
        self.assertNotIn('saveApiSettingsButton?.addEventListener("click"', script)
        self.assertNotIn('saveCodexSettingsButton?.addEventListener("click"', script)
        self.assertNotIn('codexModeNotes?.forEach', script)
        self.assertNotIn('call(methods, "selectCodexMode", note.dataset.codexModeNote)', script)
        self.assertIn("queueApiSettingsAutosave();", provider_source)
        self.assertNotIn("apiMode: document.querySelector", script)
        self.assertIn("apiProvider: document.querySelector", script)
        self.assertIn("generationProviderSelect: document.querySelector", script)
        self.assertNotIn("webSearchField: document.querySelector", script)
        self.assertIn("apiProviderName: document.querySelector", script)
        self.assertIn("apiProviderSection: document.querySelector", script)
        self.assertIn("apiProviderSearch: document.querySelector", script)
        self.assertIn("apiProviderList: document.querySelector", script)
        self.assertIn("apiProviderDetail: document.querySelector", script)
        self.assertIn("apiProviderEditor: document.querySelector", script)
        self.assertIn("editApiProviderButton: document.querySelector", script)
        self.assertIn("copyApiProviderButton: document.querySelector", script)
        self.assertIn("sortApiProvidersButton: document.querySelector", script)
        self.assertIn("cancelApiProviderEditButton: document.querySelector", script)
        self.assertIn("saveApiProviderEditButton: document.querySelector", script)
        self.assertIn("apiSettingsActions: document.querySelector", script)
        self.assertIn("function activeApiProvider", script)
        self.assertIn("function selectApiProvider", script)
        self.assertIn("function editApiProvider", script)
        self.assertIn("function copyApiProvider", script)
        self.assertIn("function toggleApiProviderSortMode", script)
        self.assertIn("function reorderApiProviders", script)
        self.assertIn("api_key_source_provider_id", script)
        self.assertIn("const copiesSavedKey = providerHasApiKey(provider)", script)
        self.assertIn('api_key_source_provider_id: copiesSavedKey ? provider.id : ""', script)
        self.assertIn("if (!provider.api_key && provider.api_key_source_provider_id)", script)
        self.assertIn("function confirmDeleteApiProvider", script)
        self.assertIn("function cancelApiProviderEdit", script)
        self.assertIn("function saveApiProviderEdit", script)
        self.assertIn("function renderApiProviderList", script)
        self.assertIn("export const API_PROVIDER_SEARCH_THRESHOLD = 10", provider_list_source)
        self.assertIn('classList.toggle("is-long-list", longList)', provider_list_source)
        self.assertIn('classList.toggle("hidden", !searchVisible)', provider_list_source)
        self.assertIn("apiProviderMatchesSearch", provider_list_source)
        self.assertIn("scrollActiveApiProviderCardIntoView", provider_list_source)
        self.assertIn("panel.scrollTo", provider_list_source)
        self.assertIn('closest<HTMLElement>(".system-settings-scroll, .system-settings-section")', provider_list_source)
        self.assertNotIn("scrollIntoView", provider_list_source)
        self.assertIn("apiProviderMatchesSearch(provider, searchQuery)", provider_source)
        self.assertIn('translate("apiSettings.noProviderSearchResults")', provider_source)
        self.assertIn('if (!searchQuery) scrollActiveApiProviderCardIntoView(settings.active_provider_id, "center")', provider_source)
        self.assertIn('scrollActiveApiProviderCardIntoView(activeApiProvider().id, "center")', provider_source)
        self.assertIn("function renderApiProviderDetail", script)
        self.assertIn("function renderApiProviderEditor", script)
        self.assertIn('apiProviderSection?.setAttribute("aria-hidden", visible ? "true" : "false")', script)
        self.assertIn('apiProviderSection?.setAttribute("inert", "")', script)
        self.assertIn('apiProviderSection?.removeAttribute("inert")', script)
        self.assertIn("function updateProviderBindingCount", script)
        self.assertIn("readProviderBindingCards(els.apiProviderBindings)", script)
        self.assertIn('setElementText(els.providerBindingsCount, `(${count})`)', script)
        self.assertIn("function setApiKeyRevealVisible", script)
        self.assertIn("function updateApiKeyRevealButton", script)
        self.assertIn("function revealApiKeyWhilePressed", script)
        self.assertIn("function hideApiKeyReveal", script)
        self.assertIn("function addApiProvider", script)
        self.assertIn("function deleteApiProvider", script)
        self.assertIn("apiProviderDraft", script)
        self.assertIn("apiProviderDraftIsNew", script)
        self.assertIn("options.applyProviderDraft", script)
        self.assertIn("readApiSettingsForm({ applyProviderDraft: !autoSave })", script)
        self.assertIn("localStorage.getItem(API_SETTINGS_STORAGE_KEY)", script)
        self.assertIn("localStorage.setItem(API_SETTINGS_STORAGE_KEY", script)
        self.assertIn("active_provider_id: state.apiSettings.active_provider_id", script)
        self.assertIn("providers: state.apiSettings.providers", script)
        self.assertIn("codex_mode: state.apiSettings.codex_mode", script)
        self.assertIn("function currentCodexMode", script)
        self.assertIn('return mode === "responses" ? "Codex Responses" : "Codex Image"', script)
        self.assertIn('providerBindingSelectionKey("codex", `codex-gpt-image-2-${normalized}`)', provider_source)
        self.assertIn("function selectCodexMode", script)
        self.assertIn("function queueApiSettingsAutosave", script)
        self.assertRegex(provider_source, r"async function deleteApiProvider\(\)[\s\S]*await saveApiSettings\(\{ auto: true, candidateSettings: candidate \}\)")
        self.assertRegex(provider_source, r"function selectApiProvider\(providerId[^)]*\)[\s\S]*queueApiSettingsAutosave\(\{ silent: true \}\);[\s\S]*function editApiProvider")
        self.assertRegex(provider_source, r"function reorderApiProviders\(orderedIds[^)]*\)[\s\S]*queueApiSettingsAutosave\(\);[\s\S]*async function saveApiProviderEdit")
        self.assertIn("const sortFocusId = autoSave ? focusedApiProviderSortId()", provider_source)
        self.assertRegex(provider_source, r"populateApiSettingsForm\(\);\s*focusApiProviderSortHandle\(sortFocusId\);")
        self.assertIn('void saveApiSettings({ auto: true, silent: options.silent })', script)
        self.assertIn('translate("apiSettings.autoSaving")', script)
        self.assertIn('translate("apiSettings.autoSaved")', script)
        self.assertIn("codexModeLabel(currentCodexMode())", script)
        self.assertIn("function setApiSettingsFeedback", script)
        self.assertIn("function setSaveButtonText", script)
        self.assertIn('saving: translate("apiSettings.saving")', script)
        self.assertIn('saved: translate("apiSettings.savedShort")', script)
        self.assertIn('default: translate("action.save")', script)
        self.assertNotRegex(script, r"saveApiSettingsButton\)[^\n]*saveApiSettingsButton\.textContent")
        self.assertRegex(script, r"saveApiProviderEditButton\)[^\n]*saveApiProviderEditButton\.textContent = providerText")
        self.assertNotRegex(script, r"saveCodexSettingsButton\)[^\n]*saveCodexSettingsButton\.textContent")
        self.assertIn('setSaveButtonText("saving")', script)
        self.assertIn('setSaveButtonText("saved")', script)
        self.assertIn('formatTranslation("apiSettings.savedSummary"', script)
        self.assertIn('fetch("/api/api-settings"', script)
        self.assertIn("openApiSettingsModal", script)
        self.assertNotIn("handleAuthSourceDoubleClick", script)
        self.assertNotIn('authSourceGroup?.addEventListener("dblclick"', script)
        self.assertIn('generationProviderSettingsButton?.addEventListener("click", () => call(methods, "openGenerationProviderSettings"))', script)
        self.assertNotIn('apiSourceSettingsButton?.addEventListener("click"', script)
        self.assertIn('apiProviderList?.addEventListener("click"', script)
        self.assertIn('apiProviderSearch?.addEventListener("input", () => call(methods, "renderApiProviderList"))', script)
        self.assertNotIn('closest?.("[data-api-provider-sort]")', event_source)
        self.assertNotIn('call(methods, "moveApiProvider"', event_source)
        self.assertIn("data-api-provider-sort-handle", provider_sort_source)
        self.assertIn("handle.dataset.apiProviderSortHandle", provider_source)
        self.assertIn('addEventListener("pointerdown"', provider_sort_source)
        self.assertIn('addEventListener("pointermove"', provider_sort_source)
        self.assertIn('addEventListener("pointerup"', provider_sort_source)
        self.assertIn('addEventListener("pointercancel"', provider_sort_source)
        self.assertIn('addEventListener("keydown"', provider_sort_source)
        self.assertIn('event.key === "Escape"', provider_sort_source)
        self.assertIn("setPointerCapture", provider_sort_source)
        self.assertNotIn("dataTransfer", provider_sort_source)
        self.assertNotIn("draggable = true", provider_sort_source)
        self.assertIn('call(methods, "selectApiProvider"', script)
        self.assertIn('editApiProviderButton?.addEventListener("click", () => call(methods, "editApiProvider"))', script)
        self.assertIn('copyApiProviderButton?.addEventListener("click", () => call(methods, "copyApiProvider"))', script)
        self.assertIn('sortApiProvidersButton?.addEventListener("click", () => call(methods, "toggleApiProviderSortMode"))', script)
        self.assertIn('deleteApiProviderButton?.addEventListener("click", () => call(methods, "confirmDeleteApiProvider", els.deleteApiProviderButton))', script)
        self.assertIn('cancelApiProviderEditButton?.addEventListener("click", () => call(methods, "cancelApiProviderEdit"))', script)
        self.assertIn('saveApiProviderEditButton?.addEventListener("click", () => call(methods, "saveApiProviderEdit"))', script)
        self.assertIn('apiKeyRevealButton?.addEventListener("pointerdown"', script)
        self.assertIn('apiKeyRevealButton?.addEventListener("pointerup"', script)
        self.assertIn('apiKeyRevealButton?.addEventListener("pointerleave"', script)
        self.assertIn('apiKeyRevealButton?.addEventListener("keydown"', script)
        self.assertIn('apiKeyRevealButton?.addEventListener("keyup"', script)
        self.assertIn('apiKey?.addEventListener("input"', script)
        self.assertNotIn("updateApiRequestEndpointPreview", script)
        self.assertIn('addProviderBindingButton?.addEventListener("click"', script)
        self.assertIn('apiProviderBindings?.addEventListener("change"', script)
        self.assertNotIn("els.apiImageModel", script)
        self.assertIn("auth_source: authSource", script)
        self.assertIn("requested_backend: requestedBackend", script)
        self.assertIn("function taskBackendValue", script)
        self.assertIn("function taskApiProviderLabel", script)
        self.assertIn("function taskBackendLabel", script)
        self.assertIn("const backend = taskBackendValue(task)", script)
        self.assertIn("const provider = taskApiProviderLabel(task)", script)
        self.assertIn("|| task?.provider_id", script)
        self.assertIn("|| task?.provider", script)
        self.assertNotIn('if (!providerId) return "";', script)
        self.assertIn('if (backend === "codex_responses") return "Codex Responses"', script)
        self.assertIn('if (backend === "openai_responses") return "API Responses"', script)
        self.assertIn('return [backendLabel, provider].filter(Boolean).join(" · ")', script)
        self.assertIn("canonical_model_id: selection.canonicalModelId", script)
        self.assertIn("provider_id: selection.providerId", script)
        self.assertIn("parameters", script)
        self.assertIn("payload.main_model = params.main_model", script)
        self.assertIn('payload.codex_mode = codexMode', script)
        self.assertNotIn('form.append("codex_mode"', script)
        self.assertNotIn('form.append("api_mode"', script)
        self.assertNotIn('form.append("api_provider_id"', script)
        self.assertNotIn('form.append("web_search"', script)
        self.assertIn('form.append("canonical_model_id", selection.canonicalModelId)', script)
        self.assertIn('form.append("provider_id", selection.providerId)', script)
        self.assertIn('form.append("parameters_json", JSON.stringify(sortedRecord(selection.parameters)))', script)
        self.assertIn("params.web_search = true", script)
        self.assertIn("payload.api_provider_name = state.generationCatalog", script)
        self.assertIn("webui_api_provider_name", script)
        self.assertIn("api_provider_name: request.api_provider_name", script)
        self.assertIn("normalizeApiImagesConcurrency(provider.concurrency ?? provider.images_concurrency)", script)
        self.assertIn("concurrency: normalizeApiImagesConcurrency(els.apiImagesConcurrency?.value)", script)
        self.assertIn("return Math.min(32, Math.max(1, parsed));", script)
        self.assertIn("params.api_images_concurrency = currentApiImagesConcurrency()", script)
        self.assertIn("concurrency: provider.concurrency", script)
        self.assertNotIn("api_image_model: currentApiImageModel()", script)
        self.assertNotIn("api_key: currentApiKey()", script)
        self.assertNotIn("api_key: activeApiProvider", script)
        self.assertIn(".api-provider-list", styles)
        self.assertIn(".api-provider-choice-grid", styles)
        self.assertIn(".api-provider-search", styles)
        self.assertIn(".api-provider-choice", styles)
        self.assertIn(".api-provider-add-button", styles)
        self.assertIn(".api-provider-detail-panel", styles)
        self.assertIn(".api-provider-detail-grid", styles)
        self.assertIn(".api-provider-detail-actions", styles)
        self.assertIn(".api-provider-section-title", styles)
        self.assertIn(".api-provider-editor", styles)
        self.assertNotIn(".provider-bindings-connection", styles)
        self.assertIn(".provider-binding-advanced", styles)
        self.assertIn(".compact-api-settings-grid", styles)
        self.assertRegex(styles, r"\.api-provider-section-header\s*\{[^}]*justify-content:\s*space-between")
        self.assertRegex(styles, r"\.api-provider-editor-heading\s*\{[^}]*justify-content:\s*flex-start")
        self.assertRegex(styles, r"\.api-provider-detail-actions,\s*\.api-provider-editor-actions\s*\{[^}]*justify-content:\s*center")
        self.assertRegex(styles, r"\.system-settings-section \.settings-save-actions\s*\{[^}]*position:\s*relative[^}]*justify-content:\s*center")
        self.assertRegex(styles, r"\.api-provider-detail-actions \.ghost-button,\s*\.api-provider-detail-actions \.danger-button,[\s\S]*height:\s*40px")
        self.assertRegex(styles, r"\.api-provider-editor-actions \.ghost-button,\s*\.api-provider-editor-actions \.run-button\s*\{[^}]*border-radius:\s*8px")
        self.assertRegex(styles, r"\.api-provider-choice-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)")
        self.assertNotRegex(styles, r"\.api-provider-choice-grid(?:\.is-long-list)?\s*\{[^}]*(?:max-height:|overflow-y:\s*auto)")
        self.assertRegex(styles, r"\.api-provider-search-empty\s*\{[^}]*grid-column:\s*1\s*/\s*-1")
        self.assertRegex(styles, r"\.api-provider-section\.editing\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.compact-api-settings-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto")
        self.assertRegex(styles, r"\.compact-api-settings-grid > \.api-provider-name-field\s*\{[^}]*grid-column:\s*1[^}]*grid-row:\s*1")
        self.assertRegex(styles, r"\.compact-api-settings-grid > \.api-concurrency-field\s*\{[^}]*grid-column:\s*2[^}]*grid-row:\s*1")
        self.assertRegex(styles, r"\.api-settings-grid\s*\{[^}]*align-items:\s*start")
        self.assertRegex(styles, r"\.api-provider-list\s*\{[^}]*display:\s*contents")
        self.assertNotRegex(styles, r"\.api-provider-list\s*\{[^}]*overflow-x:\s*auto")
        self.assertRegex(styles, r"\.api-provider-choice\.active\s*\{[^}]*background:\s*var\(--primary-light\)")
        self.assertRegex(styles, r"\.api-provider-choice\.active\s*\{[^}]*color:\s*var\(--text\)")
        self.assertRegex(styles, r"\.api-provider-choice\.active span\s*\{[^}]*color:\s*var\(--text-secondary\)")
        self.assertRegex(styles, r"\.api-provider-detail-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)")
        self.assertRegex(styles, r"\.api-provider-editor\.hidden\s*,\s*\.api-provider-detail-panel\.hidden\s*\{[^}]*display:\s*none")
        self.assertIn("const MIN_SYSTEM_SETTINGS_MODAL_EDGE = 30", script)
        self.assertIn("function positionSystemSettingsModal", script)
        self.assertIn("function animateSystemSettingsPanelHeight", script)
        self.assertIn("function systemSettingsTargetHeight", script)
        self.assertIn("window.innerHeight", script)
        self.assertIn("--system-settings-modal-top", script)
        self.assertIn("style.removeProperty(\"--system-settings-modal-top\")", script)
        self.assertIn("const wasHidden = modal?.classList.contains(\"hidden\") ?? true", script)
        self.assertIn("panel.scrollHeight", script)
        self.assertIn("(prefers-reduced-motion: reduce)", script)
        self.assertRegex(styles, r"\.api-settings-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.compact-api-settings-grid > \.api-provider-name-field,[\s\S]*?\.compact-api-settings-grid > \.api-concurrency-field\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.compact-api-settings-grid > \.api-provider-name-field,[\s\S]*?\.compact-api-settings-grid > \.api-concurrency-field\s*\{[^}]*grid-template-columns:\s*6\.5em\s+minmax\(0,\s*1fr\)[^}]*align-items:\s*center")
        self.assertRegex(
            styles,
            r"\.api-provider-name-inputs\s*\{[^}]*"
            r"grid-template-columns:\s*44px\s+minmax\(0,\s*1fr\)",
        )
        self.assertRegex(styles, r"\.api-advanced-settings\s*\{[^}]*grid-column:\s*1\s*/\s*-1")
        self.assertRegex(styles, r"\.api-advanced-settings > summary\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"@media\s*\(max-width:\s*620px\)\s*\{[\s\S]*?\.api-settings-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.api-key-input-wrap\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.api-key-input-wrap \.control\s*\{[^}]*padding-right:\s*40px")
        self.assertRegex(styles, r"\.api-key-reveal-button\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.api-key-reveal-button\s*\{[^}]*right:\s*6px")
        self.assertRegex(styles, r"#apiImagesConcurrency\s*\{[^}]*appearance:\s*textfield")
        self.assertRegex(styles, r"#apiImagesConcurrency::-webkit-outer-spin-button,\s*#apiImagesConcurrency::-webkit-inner-spin-button\s*\{[^}]*-webkit-appearance:\s*none")
        self.assertRegex(styles, r"#systemSettingsModal\s*\{[^}]*--system-settings-modal-top:\s*30px")
        self.assertRegex(styles, r"#systemSettingsModal\s*\{[^}]*align-items:\s*flex-start")
        self.assertRegex(styles, r"#systemSettingsModal\s*\{[^}]*overflow:\s*auto")
        self.assertRegex(styles, r"#systemSettingsModal\s*\{[^}]*padding-block:\s*var\(--system-settings-modal-top,\s*30px\)\s+30px")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*\{[^}]*padding:\s*22px\s+28px\s+24px")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s*\{[^}]*justify-content:\s*center")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s*\{[^}]*min-height:\s*44px")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s*\{[^}]*margin-bottom:\s*16px")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s*\{[^}]*text-align:\s*center")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s+\.drawer-close-button\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.system-settings-scroll\s*\{[^}]*scrollbar-gutter:\s*stable both-edges")
        self.assertNotIn(".system-settings-section-heading", styles)
        self.assertRegex(styles, r"\.system-settings-tabs\s*\{[^}]*grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)")
        self.assertRegex(
            styles,
            r"@media \(max-width:\s*520px\)\s*\{[\s\S]*?\.system-settings-tabs\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)",
        )
        self.assertRegex(styles, r"\.system-settings-tabs\s*\{[^}]*--segmented-indicator-radius:\s*999px")
        self.assertRegex(styles, r"\.system-settings-tab\.active\s*\{[^}]*color:\s*var\(--primary-foreground\)")
        self.assertRegex(styles, r"\.system-settings-tabs\s+\.segmented-indicator\s*\{[^}]*border-radius:\s*999px")
        self.assertNotIn(".codex-channel-notes", styles)
        self.assertNotIn(".codex-channel-note.active", styles)
        self.assertNotIn(".codex-channel-current", styles)
        self.assertRegex(styles, r"\.api-provider-section-header\s*\{[^}]*justify-content:\s*space-between")
        self.assertRegex(styles, r"\.api-provider-sort-toggle,\s*\.api-provider-add-button\s*\{[^}]*min-width:\s*72px")
        self.assertRegex(styles, r"\.api-provider-list\.is-sorting\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.api-provider-sort-row\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+36px")
        self.assertRegex(styles, r"\.api-provider-sort-handle\s*\{[^}]*touch-action:\s*none")
        self.assertRegex(styles, r"\.api-provider-sort-drag-layer\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.api-provider-sort-drag-layer\s*\{[^}]*pointer-events:\s*none")
        self.assertRegex(styles, r"\.api-provider-sort-drag-preview\s*\{[^}]*box-shadow:\s*var\(--shadow-popover\)")
        self.assertRegex(styles, r"\.api-provider-sort-drag-preview\s*\{[^}]*will-change:\s*transform")
        self.assertRegex(styles, r"@media \(prefers-reduced-motion:\s*reduce\)[\s\S]*?\.api-provider-sort-row\.is-dragging")
        self.assertNotIn(".api-provider-sort-button", styles)
        self.assertRegex(styles, r"\.model-tool-row\s*\{[^}]*flex-wrap:\s*wrap")
        self.assertIn(".web-search-toggle", styles)
        # Toggle parameters reuse the shared switch styling.
        renderer = Path("codex_image/webui/frontend/src/model-parameters.ts").read_text(encoding="utf-8")
        self.assertIn('label.className = "web-search-toggle model-parameter-toggle"', renderer)
        self.assertIn('track.className = "web-search-toggle-track"', renderer)
        self.assertNotIn('data-i18n="output.webSearchToggle"', html)
        self.assertIn(".web-search-toggle:has(input:focus-visible)", styles)
        self.assertNotIn(".api-direct-settings-notice", styles)
        self.assertIn(".api-settings-feedback.ok", styles)
        self.assertIn(".api-settings-feedback.error", styles)
        self.assertIn(".api-settings-feedback.running", styles)
        self.assertRegex(styles, r"\.api-settings-feedback:empty\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.settings-action-status\s*\{[^}]*flex:\s*1 1 auto")
        self.assertRegex(styles, r"\.settings-action-status\s*\{[^}]*white-space:\s*nowrap")
        self.assertRegex(styles, r"\.settings-action-status:empty\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.settings-modal-actions\s+\.run-button\s*\{[^}]*justify-content:\s*center")
        self.assertRegex(styles, r"\.settings-modal-actions\s+\.run-button\s*\{[^}]*text-align:\s*center")
    def test_primary_panel_close_buttons_use_consistent_x_button(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        expected_buttons = {
            "archiveModalClose": "关闭会话归档面板",
            "systemSettingsModalClose": "关闭系统设置面板",
            "imageEditorClose": "关闭编辑输入图片面板",
            "galleryDrawerClose": "关闭公用图库面板",
            "addToGalleryClose": "关闭添加到图库面板",
        }
        for button_id, aria_label in expected_buttons.items():
            with self.subTest(button_id=button_id):
                self.assertCloseButtonUsesConsistentX(html, button_id, aria_label)

        self.assertNotIn('class="ghost-button text-sm" type="button">关闭</button>', html)
        self.assertRegex(styles, r"\.drawer-close-button\s*\{[^}]*flex:\s*0 0 44px")
        self.assertRegex(styles, r"\.drawer-close-button\s*\{[^}]*min-width:\s*44px")
        self.assertRegex(styles, r"\.drawer-close-button\s*\{[^}]*align-items:\s*center")
        self.assertRegex(styles, r"\.drawer-close-icon\s*\{[^}]*stroke:\s*currentColor")

    def test_button_radio_groups_are_not_wrapped_by_labels(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")

        for label_html in re.findall(r"<label\b[\s\S]*?</label>", html):
            self.assertNotIn('class="radio-group"', label_html)
            self.assertNotIn('class="radio-btn"', label_html)
    def test_right_column_size_reference_panels_are_removed(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")

        self.assertNotIn("尺寸约束", html)
        self.assertNotIn("常用尺寸", html)
        self.assertNotIn('data-size=', html)
        self.assertNotIn("size-panels-container", html)
    def test_lightbox_is_fixed_overlay(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertRegex(styles, r"\.history-lightbox\s*\{[^}]*position:\s*fixed", "shared lightbox should float over the viewport")
        self.assertRegex(styles, r"\.history-lightbox\[hidden\]\s*\{[^}]*display:\s*none", "shared lightbox should be hidden when inactive")
        self.assertRegex(styles, r"\.history-lightbox-close\s*\{[^}]*position:\s*absolute", "close button should stay inside the overlay")
        self.assertRegex(styles, r"\.history-lightbox-close\s*\{[^}]*display:\s*inline-flex", "close icon should not rely on glyph line-height")
        self.assertRegex(styles, r"\.history-lightbox-close\s*\{[^}]*align-items:\s*center", "close icon should be vertically centered")
        self.assertRegex(styles, r"\.history-lightbox-close\s*\{[^}]*justify-content:\s*center", "close icon should be horizontally centered")

    def test_lightbox_can_close_with_button_and_escape(self) -> None:
        lightbox_source = self._lightbox_source()
        shared_source = Path("codex_image/webui/frontend/src/history-lightbox.ts").read_text(encoding="utf-8")

        self.assertIn("closeHistoryLightbox", lightbox_source)
        self.assertIn('addEventListener("click", closeHistoryLightbox)', shared_source)
        self.assertIn('addEventListener("keydown"', shared_source)
        self.assertIn('event.key === "Escape"', shared_source)
        self.assertIn('class="drawer-close-icon"', shared_source)
        self.assertIn('<path d="M6 6l12 12M18 6L6 18"></path>', shared_source)
        self.assertNotIn('aria-label="${translate("lightbox.close")}">×</button>', shared_source)

    def test_lightbox_can_navigate_multiple_outputs(self) -> None:
        script = self._frontend_script_source()
        lightbox_source = self._lightbox_source()
        shared_source = Path("codex_image/webui/frontend/src/history-lightbox.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('const images = [...els.previewGrid.querySelectorAll("[data-lightbox-url]")]', script)
        self.assertIn("window.openLightbox?.(currentUrl, urls, Math.max(0, images.indexOf(image)), {", script)
        self.assertIn('from "./history-lightbox"', lightbox_source)
        self.assertIn("openHistoryLightbox(", lightbox_source)
        self.assertIn('data-history-lightbox-slot="previous"', shared_source)
        self.assertIn('data-history-lightbox-slot="current"', shared_source)
        self.assertIn('data-history-lightbox-slot="next"', shared_source)
        self.assertIn('event.key === "ArrowLeft"', shared_source)
        self.assertIn('event.key === "ArrowRight"', shared_source)
        self.assertNotIn('class="lightbox-nav', lightbox_source)
        self.assertNotIn(".lightbox-nav", styles)
        self.assertRegex(styles, r"\.history-lightbox-counter\s*\{[^}]*position:\s*absolute")

    def test_generation_lightbox_shares_zoom_and_task_navigation_controls(self) -> None:
        lightbox_source = self._lightbox_source()
        selection_source = Path("codex_image/webui/frontend/src/task-selection.ts").read_text(encoding="utf-8")
        preview_source = Path("codex_image/webui/frontend/src/task-preview.ts").read_text(encoding="utf-8")

        self.assertIn('from "./history-lightbox"', lightbox_source)
        self.assertIn("openMainTaskLightboxByDirection", selection_source)
        self.assertIn("onTaskNavigate: openMainTaskLightboxByDirection", selection_source)
        self.assertIn('onTaskNavigate: (direction, context) => legacyMethod("openMainTaskLightboxByDirection", direction, context)', preview_source)

    def test_lightbox_controls_stay_above_zoomed_image(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertRegex(styles, r"\.history-lightbox\s+img\s*\{[^}]*z-index:\s*1")
        self.assertRegex(styles, r"\.history-lightbox-close\s*\{[^}]*z-index:\s*2")
        self.assertRegex(styles, r"\.history-lightbox-peek\s*\{[^}]*z-index:\s*1")
        self.assertRegex(styles, r"\.history-lightbox-counter\s*\{[^}]*z-index:\s*2")
    def test_lightbox_right_click_does_not_leave_image_panning(self) -> None:
        shared_source = Path("codex_image/webui/frontend/src/history-lightbox.ts").read_text(encoding="utf-8")

        self.assertIn("function stopHistoryLightboxPanning", shared_source)
        self.assertIn("if (event.button !== 0)", shared_source)
        self.assertIn('image?.addEventListener("contextmenu", stopHistoryLightboxPanning)', shared_source)
        self.assertIn('window.addEventListener("mouseup", stopHistoryLightboxPanning)', shared_source)
        self.assertIn('window.addEventListener("blur", stopHistoryLightboxPanning)', shared_source)
        self.assertIn("event.buttons !== undefined && (event.buttons & 1) !== 1", shared_source)
    def test_simplified_workspace_removes_unneeded_panels(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")

        self.assertNotIn("基础设置", html)
        self.assertNotIn("接口模式", html)
        self.assertNotIn("任务类型", html)
        self.assertNotIn("状态</h2>", html)
        self.assertNotIn("接口请求预览", html)
        self.assertNotIn("copyJsonButton", html)
        # The model is chosen in the catalog selectors; no hidden GPT model field remains.
        self.assertNotIn('id="model"', html)
    def test_dashboard_uses_two_column_workspace(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        shell = self._shell_ui_source()
        layout = Path("codex_image/webui/static/styles/30-layout-top-nav-panels.css").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("controls-col", html)
        self.assertIn("preview-col", html)
        self.assertIn("controlsCol: document.querySelector", script)
        self.assertIn("previewCol: document.querySelector", script)
        self.assertIn("previewPanel: document.querySelector", script)
        self.assertNotIn("setupPreviewPanelHeightSync", shell)
        self.assertNotIn("syncPreviewPanelHeight", shell)
        self.assertNotIn("--controls-col-height", shell)
        self.assertNotIn('class="settings-panel"', html)
        self.assertNotIn('class="status-panel"', html)
        self.assertNotIn('class="json-panel"', html)
        self.assertRegex(styles, r"\.dashboard\s*\{[^}]*width:\s*min\(100%,\s*1760px\)")
        self.assertRegex(styles, r"\.dashboard\s*\{[^}]*margin-inline:\s*auto")
        self.assertRegex(styles, r"\.dashboard\s*\{[^}]*grid-template-columns:\s*minmax\(520px,\s*760px\)\s+minmax\(520px,\s*1fr\)")
        self.assertRegex(styles, r"\.dashboard\s*\{[^}]*min-height:\s*0")
        # The two-column workspace has no rows; only the desktop studio layout stacks stage and composer.
        self.assertNotRegex(layout, r"\.dashboard\s*\{[^}]*grid-template-rows:")
        self.assertRegex(styles, r"\.dashboard\s*\{[^}]*align-content:\s*safe center")
        self.assertRegex(styles, r"\.dashboard\s*\{[^}]*align-items:\s*stretch")
        self.assertRegex(styles, r"\.controls-col\s*\{[^}]*max-width:\s*760px")
        self.assertRegex(styles, r"\.controls-col\s*\{[^}]*width:\s*100%")
        controls_block = self._extract_css_block(styles, ".controls-col")
        self.assertNotIn("height:", controls_block)
        self.assertNotIn("overflow-y:", controls_block)
        self.assertRegex(
            layout,
            r"\.controls-col\s+\.image-panel,\s*\.controls-col\s+\.prompt-panel\s*\{[^}]*"
            r"display:\s*flex[^}]*flex-direction:\s*column",
        )
        self.assertRegex(
            layout,
            r"\.controls-col\s+\.image-panel\s*\{[^}]*flex:\s*1\s+1\s+"
            r"var\(--compact-image-panel-height,\s*276px\)",
        )
        self.assertRegex(
            layout,
            r"\.controls-col\s+\.prompt-panel\s*\{[^}]*flex:\s*1\.15\s+1\s+"
            r"var\(--compact-prompt-panel-height,\s*260px\)",
        )
        self.assertRegex(
            layout,
            r"\.controls-col\s+\.output-panel\s*\{[^}]*flex:\s*0\s+0\s+auto",
        )
        self.assertNotRegex(styles, r"\.controls-col\s*>\s*\.output-panel\s*\{[^}]*flex:\s*1\s+1\s+auto")
        self.assertNotRegex(styles, r"\.preview-col\s*\{[^}]*position:\s*sticky")
        self.assertRegex(styles, r"\.preview-col\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.preview-col\s*\{[^}]*height:\s*auto")
        self.assertRegex(styles, r"\.preview-col\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.preview-panel\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.preview-panel\s*\{[^}]*inset:\s*0")
        self.assertRegex(styles, r"\.preview-panel\s*\{[^}]*height:\s*auto")
        self.assertRegex(styles, r"\.preview-panel\s*\{[^}]*max-height:\s*none")
        self.assertRegex(styles, r"\.preview-panel\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.preview-grid\s*\{[^}]*flex:\s*1")
        self.assertRegex(styles, r"\.preview-grid\s*\{[^}]*min-height:\s*0")
        self.assertRegex(styles, r"\.preview-grid\s*\{[^}]*place-items:\s*center")
        self.assertRegex(styles, r"\.preview-grid\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.preview-grid:not\(\.multi-output\)\s+\.preview-card\s*\{[^}]*height:\s*100%")
        self.assertRegex(styles, r"\.preview-grid:not\(\.multi-output\)\s+\.preview-card\s*\{[^}]*border-color:\s*transparent")
        self.assertRegex(styles, r"\.preview-grid:not\(\.multi-output\)\s+\.preview-card\s*\{[^}]*background:\s*transparent")
        self.assertRegex(styles, r"\.preview-grid:not\(\.multi-output\)\s+\.preview-card img\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.preview-grid:not\(\.multi-output\)\s+\.preview-card img\s*\{[^}]*inset:\s*0")
        self.assertRegex(styles, r"\.preview-grid:not\(\.multi-output\)\s+\.preview-card img\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.preview-grid:not\(\.multi-output\)\s+\.preview-card img\s*\{[^}]*height:\s*100%")
        self.assertRegex(styles, r"\.preview-card\s*\{[^}]*max-height:\s*100%")
        self.assertRegex(styles, r"\.preview-card\s*\{[^}]*border:\s*1px solid transparent")
        self.assertRegex(styles, r"\.preview-card img\s*\{[^}]*max-width:\s*100%")
        self.assertRegex(styles, r"\.preview-card img\s*\{[^}]*max-height:\s*100%")
        self.assertNotIn(".preview-col > .panel:last-child", styles)

    def test_desktop_studio_layout_docks_composer_below_results(self) -> None:
        manifest = json.loads(Path("codex_image/webui/static/styles/manifest.json").read_text(encoding="utf-8"))
        studio = Path("codex_image/webui/static/styles/85-studio.css").read_text(encoding="utf-8")
        composer = Path("codex_image/webui/frontend/src/studio-composer.ts").read_text(encoding="utf-8")
        main = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        # The studio stylesheet must follow the responsive rules it overrides.
        self.assertLess(manifest.index("80-utilities-responsive.css"), manifest.index("85-studio.css"))
        self.assertIn('STUDIO_QUERY = "(min-width: 1181px)"', composer)
        self.assertIn("initStudioComposer();", main)
        self.assertRegex(
            studio,
            r"body\[data-studio\] \.dashboard\s*\{[^}]*grid-template-rows:\s*minmax\(0,\s*1fr\)\s+auto",
        )
        self.assertRegex(studio, r"body\[data-studio\] \.preview-col\s*\{[^}]*grid-row:\s*1")
        self.assertRegex(studio, r"body\[data-studio\] \.controls-col\s*\{[^}]*grid-row:\s*2")
        # Parameters stay laid out while closed so segment indicators can measure.
        self.assertRegex(
            studio,
            r"body\[data-studio\] \.controls-col \.output-panel\s*\{[^}]*visibility:\s*hidden",
        )
        # Clear / find / recent templates / template library stay reachable.
        template_row = self._extract_css_block(studio, "body[data-studio] .prompt-panel .prompt-template-row")
        self.assertNotIn("display: none", template_row)
        self.assertRegex(studio, r"body\[data-studio\] \.compact-preview-jump\s*\{[^}]*display:\s*none")
        # Controls are moved back when leaving the desktop width.
        self.assertIn('document.createComment("studio-run-origin")', composer)
        self.assertIn("runMarker.replaceWith(runButton)", composer)

    def test_main_workspace_uses_theme_background_texture_only(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        dashboard_block = self._extract_css_block(styles, ".dashboard")

        self.assertRegex(styles, r":root\s*\{[\s\S]*--workspace-texture:\s*radial-gradient")
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\]\s*\{[\s\S]*--workspace-texture:\s*radial-gradient")
        self.assertRegex(styles, r"\.main-wrapper\s*\{[^}]*background-image:\s*var\(--workspace-texture\)")
        self.assertRegex(styles, r"\.main-wrapper\s*\{[^}]*background-size:\s*22px 22px,\s*100% 100%")
        self.assertNotIn("background-image: var(--workspace-texture)", dashboard_block)
        self.assertNotIn("--preview-panel-texture", styles)
        self.assertNotIn(".preview-col > .panel.preview-panel", styles)
    def test_destructive_actions_use_anchored_web_confirm_popover(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotIn("window.confirm", script)
        self.assertIn("function openConfirmPopover", script)
        self.assertIn("function closeConfirmPopover", script)
        self.assertIn("positionConfirmPopover(anchor, popover)", script)
        self.assertIn('data-confirm-popover-confirm', script)
        self.assertIn('data-confirm-popover-cancel', script)
        self.assertIn("openConfirmPopover(deleteButton", script)
        self.assertIn("openConfirmPopover(els.batchDeleteButton", script)
        self.assertIn("openConfirmPopover(button", script)
        self.assertRegex(styles, r"\.confirm-popover\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.confirm-popover\s*\{[^}]*z-index:\s*9300")
        self.assertRegex(styles, r"\.confirm-popover-actions\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.confirm-popover-confirm\.danger-button\s*\{[^}]*background:")
    def test_system_settings_storage_tab_can_manage_storage_paths(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotIn('id="settingsButton"', html)
        self.assertIn('id="systemSettingsModal"', html)
        self.assertIn('id="systemSettingsStoragePanel"', html)
        self.assertIn('id="settingsInputRoot"', html)
        self.assertIn('id="settingsOutputRoot"', html)
        self.assertIn('id="settingsGalleryRoot"', html)
        self.assertIn('id="settingsSourceDataRoot"', html)
        self.assertIn('id="saveSettingsButton"', html)
        self.assertIn('openSystemSettingsModal("storage")', script)
        self.assertIn('fetch("/api/settings")', script)
        self.assertIn('fetch("/api/settings", {', script)
        self.assertIn("restart_required", script)
        self.assertIn("重启 WebUI 后生效", script)
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*\{[^}]*width:\s*min\(624px,\s*calc\(100vw - 60px\)\)")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*\{[^}]*max-height:\s*min\(760px,\s*calc\(100vh - var\(--system-settings-modal-top,\s*30px\) - 30px\)\)")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.system-settings-scroll\s*\{[^}]*overflow-y:\s*auto")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*\{[^}]*padding:\s*22px\s+28px\s+24px")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*\{[^}]*transition:\s*height var\(--motion-height\)")
        self.assertRegex(styles, r"\.system-settings-modal-panel\.is-height-animating\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s*\{[^}]*align-items:\s*center")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s*\{[^}]*justify-content:\s*center")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s*\{[^}]*margin-bottom:\s*16px")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s+h2\s*\{[^}]*margin:\s*0")
        self.assertIn(".system-settings-tabs", styles)
        self.assertIn(".system-settings-section[hidden]", styles)
        self.assertRegex(styles, r"\.system-settings-section\s*\{[^}]*flex:\s*0 1 auto")
        self.assertRegex(styles, r"\.system-settings-section\s*\{[^}]*max-height:\s*calc\(100vh - 190px\)")
        self.assertRegex(styles, r"\.system-settings-scroll\s*\{[^}]*overflow-x:\s*hidden")
        self.assertRegex(styles, r"\.system-settings-scroll\s*\{[^}]*overflow-y:\s*auto")
        self.assertRegex(styles, r"\.system-settings-scroll\s*\{[^}]*scrollbar-gutter:\s*stable both-edges")
        self.assertRegex(styles, r"\.settings-modal-actions\s*\{[^}]*margin-top:\s*16px")
        self.assertRegex(styles, r"\.settings-path-grid\s*\{[^}]*display:\s*grid")
    def test_image_input_accepts_clipboard_images(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="pasteClipboardButton"', html)
        self.assertIn('id="statusText"', html)
        self.assertRegex(
            html,
            r'<div class="task-history-tools">\s*<div id="statusText" class="status-text" aria-live="polite" data-i18n="status\.waiting">等待任务</div>',
        )
        self.assertRegex(
            html,
            r'<div class="image-input-actions">\s*<button id="clearImagesButton" class="ghost-button icon-text-button text-sm quiet-danger-button"[\s\S]*<svg[\s\S]*<span[^>]*>清空</span>[\s\S]*?</button>\s*<button id="pasteClipboardButton" class="ghost-button icon-text-button text-sm"[\s\S]*<svg[\s\S]*<span[^>]*>粘贴</span>',
        )
        self.assertNotIn("粘贴剪贴板", html)
        self.assertIn("点击、拖入或粘贴图片", html)
        self.assertIn("pasteClipboardButton: document.querySelector(\"#pasteClipboardButton\")", script)
        self.assertIn('els.pasteClipboardButton?.addEventListener("click", pasteClipboardImages)', script)
        self.assertIn('document.addEventListener("paste", handleImagePaste)', script)
        self.assertIn('els.imageUploaderGrid?.addEventListener("dragenter", handleImageDragEnter)', script)
        self.assertIn('els.imageUploaderGrid?.addEventListener("dragover", handleImageDragOver)', script)
        self.assertIn('els.imageUploaderGrid?.addEventListener("dragleave", handleImageDragLeave)', script)
        self.assertIn('els.imageUploaderGrid?.addEventListener("drop", handleImageDrop)', script)
        self.assertIn("function isImageFile(file)", script)
        self.assertIn("function addImageFiles(files, options = {})", script)
        self.assertIn("function handleImagePaste(event)", script)
        self.assertIn("event.clipboardData?.items", script)
        self.assertIn("function dataTransferHasFile(dataTransfer)", script)
        self.assertRegex(script, r"function handleImageDragOver\(event(?:: DragEvent)?\)")
        self.assertIn("event.preventDefault()", script)
        self.assertIn('event.dataTransfer.dropEffect = "copy"', script)
        self.assertNotIn('event.dataTransfer.dropEffect = acceptsImage ? "copy" : "none"', script)
        self.assertRegex(script, r"function handleImageDrop\(event(?:: DragEvent)?\)")
        self.assertIn("event.dataTransfer", script)
        self.assertIn("inputSource.droppedCount", script)
        self.assertIn("inputSource.dropImagesOnly", script)
        self.assertIn("function pasteClipboardImages()", script)
        self.assertIn("navigator.clipboard?.read", script)
        self.assertIn("readClipboardImageFiles", script)
        self.assertIn("function focusImagePasteTarget()", script)
        self.assertIn("els.imageUploadSource?.focus({ preventScroll: true })", script)
        self.assertIn("clipboardPasteShortcutLabel", script)
        self.assertIn("图片输入区已聚焦，请按", script)
        self.assertIn("clipboardImageFilename", script)
        self.assertRegex(styles, r"\.image-uploader-grid\.drag-over\s+\.upload-tile\s*\{[^}]*background:")
    def test_image_thumbnails_keep_natural_aspect_ratio(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotRegex(styles, r"\.task-thumb\s*\{[^}]*height:\s*44px")
        self.assertNotRegex(styles, r"\.preview-card\s*\{[^}]*aspect-ratio:\s*1")
        self.assertRegex(styles, r"\.task-thumb\s*\{[^}]*object-fit:\s*contain")
        self.assertRegex(styles, r"\.preview-card img\s*\{[^}]*height:\s*auto")
    def test_javascript_tolerates_removed_status_and_json_panels(self) -> None:
        script = self._frontend_script_source()

        self.assertIn("if (!els.statusText) return", script)
        self.assertIn('setMode("generate")', script)
    def test_input_image_editor_modal_markup_and_styles_exist(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="imageEditorModal"', html)
        self.assertIn('aria-label="编辑输入图片"', html)
        self.assertIn('id="imageEditorCanvas"', html)
        self.assertIn('id="imageEditorCanvasWrap"', html)
        self.assertIn('id="imageEditorToolBrush"', html)
        self.assertIn('id="imageEditorToolArrow"', html)
        self.assertIn('id="imageEditorToolCrop"', html)
        self.assertIn('id="imageEditorToolFill"', html)
        self.assertRegex(html, r'id="imageEditorToolBrush" class="ghost-button text-sm image-editor-tool"')
        self.assertRegex(html, r'id="imageEditorToolCrop" class="ghost-button text-sm image-editor-tool active"')
        self.assertIn('data-tool-icon="brush"', html)
        self.assertIn('data-tool-icon="arrow"', html)
        self.assertIn('data-tool-icon="crop"', html)
        self.assertIn('data-tool-icon="fill"', html)
        self.assertIn('data-image-editor-tool="fill"', html)
        self.assertIn('aria-label="油漆桶填充"', html)
        self.assertIn("油漆桶", html)
        self.assertIn('id="imageEditorColor"', html)
        self.assertIn('id="imageEditorStroke"', html)
        self.assertIn('id="imageEditorStroke" class="slider" type="range" min="2" max="96" step="1" value="8"', html)
        self.assertIn('id="imageEditorUndo"', html)
        self.assertIn('id="imageEditorRedo"', html)
        self.assertIn('id="imageEditorReset"', html)
        self.assertIn('id="imageEditorSave"', html)
        self.assertIn('id="imageEditorCancel"', html)
        self.assertIn('data-image-editor-canvas-scope="base"', html)
        self.assertIn('data-image-editor-canvas-scope="fit"', html)
        self.assertIn('data-i18n="imageEditor.canvasScope"', html)
        self.assertRegex(styles, r"\.image-editor-panel\s*\{[^}]*width:\s*min\(1040px,\s*94vw\)")
        self.assertRegex(styles, r"\.image-editor-toolbar\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.image-editor-stage\s*\{[^}]*min-height:\s*360px")
        self.assertRegex(styles, r"\.image-editor-canvas-wrap\s*\{[^}]*touch-action:\s*none")
        self.assertRegex(styles, r"\.image-editor-canvas\s*\{[^}]*max-width:\s*100%")
        self.assertRegex(styles, r"\.image-editor-tool\.active\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.image-editor-tool\s*\{[^}]*min-height:\s*44px")
        self.assertRegex(styles, r"\.image-editor-tool\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.image-editor-tool-icon\s+svg\s*\{[^}]*width:\s*18px")
        self.assertRegex(styles, r"\.image-editor-canvas-scope-control\s*\{[^}]*grid-template-columns:\s*1fr 1fr")
        self.assertRegex(styles, r"\.image-editor-canvas-scope-control \.ghost-button\.active\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.image-editor-actions \.ghost-button,\s*\.image-editor-actions \.primary-button\s*\{[^}]*width:\s*72px")
        self.assertRegex(styles, r"\.image-editor-actions \.ghost-button,\s*\.image-editor-actions \.primary-button\s*\{[^}]*height:\s*44px")
        self.assertRegex(styles, r"\.thumb-edited-badge\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.thumb-edited-badge\s*\{[^}]*color:\s*var\(--primary-foreground\)")
        self.assertRegex(styles, r"\.thumb-edited-badge\s*\{[^}]*right:\s*5px")
        self.assertRegex(styles, r"\.thumb-edited-badge\s*\{[^}]*bottom:\s*5px")
        self.assertNotRegex(styles, r"\.thumb-edited-badge\s*\{[^}]*left:\s*5px")
        self.assertNotRegex(styles, r"\.thumb-edited-badge\s*\{[^}]*bottom:\s*31px")
    def test_input_image_thumbnail_primary_click_opens_editor_and_gallery_action_is_secondary(self) -> None:
        script = self._frontend_script_source()
        image_strip_source = self._image_strip_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("createThumbAddIcon", image_strip_source)
        self.assertIn("function createThumbRemoveIcon()", image_strip_source)
        self.assertIn("thumb-add-icon", image_strip_source)
        self.assertIn("thumb-remove-icon", image_strip_source)
        self.assertIn('data-ui-icon="close"', image_strip_source)
        self.assertIn('href="/static/icons/ui.svg?v=1#close"', image_strip_source)
        self.assertIn('remove.append(createThumbRemoveIcon())', image_strip_source)
        self.assertIn('remove.setAttribute("aria-label", translate("imageInput.removeImage"))', image_strip_source)
        self.assertNotIn('remove.textContent = "×"', image_strip_source)
        self.assertNotIn("createThumbActionIcon", script)
        self.assertNotIn('createThumbActionIcon("gallery")', script)
        self.assertNotIn('createThumbActionIcon("edit")', script)
        self.assertNotIn('className = "thumb-edit"', script)
        self.assertIn('wrapper.classList.add("editable-thumb")', script)
        self.assertIn('wrapper.tabIndex = 0', script)
        self.assertIn('wrapper.setAttribute("role", "button")', script)
        self.assertRegex(script, r"wrapper\.addEventListener\(\"click\", \(event\) => \{[\s\S]*event\.target\.closest\(\"button\"\)[\s\S]*legacyMethod\(\"openImageEditor\", index\)")
        self.assertRegex(script, r"wrapper\.addEventListener\(\"keydown\", \(event\) => \{[\s\S]*event\.key === \"Enter\"[\s\S]*legacyMethod\(\"openImageEditor\", index\)")
        self.assertIn('addToGallery.append(createThumbAddIcon(), document.createTextNode(translate("imageInput.addToGalleryShort")))', script)
        self.assertIn('translate("imageInput.addToGallery")', script)
        self.assertNotIn('document.createTextNode("+ 图库")', script)
        self.assertNotIn('document.createTextNode("加入图库")', script)
        self.assertRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*height:\s*32px")
        self.assertRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*min-width:\s*54px")
        self.assertRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*opacity:\s*1;")
        self.assertRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*pointer-events:\s*auto")
        self.assertNotRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*opacity:\s*0(?:;|$)")
        self.assertRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*bottom:\s*6px")
        self.assertRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*right:\s*auto")
        self.assertNotRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*top:\s*6px")
        self.assertRegex(styles, r"\.thumb:hover\s+\.add-upload-to-gallery,\s*\.thumb:focus-within\s+\.add-upload-to-gallery,\s*\.add-upload-to-gallery:focus-visible\s*\{[^}]*opacity:\s*1")
        self.assertRegex(styles, r"\.thumb \.thumb-remove\s*\{[^}]*z-index:\s*3")
        self.assertRegex(styles, r"\.thumb \.thumb-remove\s*\{[^}]*background:\s*color-mix\(in srgb, var\(--danger\) 78%, var\(--surface\)\)")
        self.assertRegex(styles, r"\.thumb \.thumb-remove\s*\{[^}]*color:\s*var\(--primary-foreground\)")
        self.assertNotRegex(styles, r"\.thumb \.thumb-remove\s*\{[^}]*background:\s*rgba\(0,\s*0,\s*0,\s*0\.5\)")
        self.assertRegex(styles, r"\.thumb-remove-icon,\s*\.thumb-remove-icon svg\s*\{[^}]*width:\s*14px")
        self.assertRegex(styles, r"\.thumb-badge\s*\{[^}]*background:\s*color-mix\(in srgb, var\(--primary\) 88%, transparent\)")
        self.assertRegex(styles, r"\.thumb-badge\s*\{[^}]*color:\s*var\(--primary-foreground\)")
        self.assertNotRegex(styles, r"\.thumb-badge\s*\{[^}]*background:\s*rgba\(31,\s*53,\s*47")
        self.assertRegex(styles, r"\.thumb-add-icon\s+svg\s*\{[^}]*width:\s*14px")
        self.assertRegex(styles, r"\.upload-tile\s+\.icon\s+svg\s*\{[^}]*width:\s*18px")
        self.assertRegex(styles, r"\.upload-tile\s+\.icon\s+svg\s*\{[^}]*height:\s*18px")
        self.assertNotIn(".thumb-action-icon", styles)
        self.assertRegex(styles, r"\.editable-thumb\s*\{[^}]*cursor:\s*pointer")
        self.assertRegex(styles, r"\.editable-thumb:hover\s*\{[^}]*transform:\s*translateY\(-1px\)")
        self.assertNotRegex(styles, r"\.thumb-edit\s*[,{\n]")
        self.assertNotRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*height:\s*22px")
    def test_input_image_editor_javascript_contract_exists(self) -> None:
        script = self._frontend_script_source()
        image_editor_source = self._image_editor_source()
        legacy_source = self._bootstrap_source()

        self.assertIn("IMAGE_EDITOR_PROMPT_HINT", script)
        self.assertIn("IMAGE_EDITOR_MAX_EXPORT_EDGE", script)
        self.assertIn("export function initImageEditorFeature", image_editor_source)
        self.assertIn("Object.assign(getLegacyBridge().methods", image_editor_source)
        self.assertIn("isEditableImageSource,", image_editor_source)
        for function_name in [
            "openImageEditor",
            "closeImageEditor",
            "setImageEditorTool",
            "renderImageEditor",
            "pushImageEditorHistory",
            "saveImageEdit",
            "resetImageEdit",
        ]:
            self.assertNotRegex(legacy_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn('isEditableImageSource: proxy("isEditableImageSource")', legacy_source)
        self.assertNotIn("IMAGE_EDITOR_BUCKET_FILL_TOLERANCE", script)
        self.assertIn("const imageEditorState = {", script)
        self.assertIn("brushBoundaryCanvas: null", script)
        self.assertIn("brushOverlayCanvas: null", script)
        self.assertIn('tool: "crop"', script)
        self.assertIn('canvasScope: "base"', script)
        self.assertNotIn('tool: "brush"', script)
        self.assertIn("hasInstructionMarks: false", script)
        self.assertIn("imageEditorModal: document.querySelector(\"#imageEditorModal\")", script)
        self.assertIn("imageEditorCanvas: document.querySelector(\"#imageEditorCanvas\")", script)
        self.assertIn("imageEditorToolBrush: document.querySelector(\"#imageEditorToolBrush\")", script)
        self.assertIn("imageEditorToolArrow: document.querySelector(\"#imageEditorToolArrow\")", script)
        self.assertIn("imageEditorToolCrop: document.querySelector(\"#imageEditorToolCrop\")", script)
        self.assertIn("imageEditorToolFill: document.querySelector(\"#imageEditorToolFill\")", script)
        self.assertIn("originalFile: file", script)
        self.assertIn("edited: false", script)
        self.assertIn("function openImageEditor(index)", script)
        self.assertIn("function closeImageEditor()", script)
        self.assertIn("function setImageEditorTool(tool)", script)
        self.assertIn("function renderImageEditor()", script)
        self.assertIn("function pushImageEditorHistory()", script)
        self.assertIn("function undoImageEdit()", script)
        self.assertIn("function redoImageEdit()", script)
        self.assertIn("function resetImageEdit()", script)
        self.assertIn("function saveImageEdit()", script)
        self.assertIn("function paintBucketFillRegion(point:", image_editor_source)
        self.assertIn("function imageEditorBucketFillColor(color)", script)
        self.assertIn("function imageEditorBrushBoundaryContext()", script)
        self.assertIn("function imageEditorBrushOverlayContext()", script)
        self.assertIn("function drawEditorBrushBoundarySegment(from, to)", script)
        self.assertIn("function drawEditorBrushOverlaySegment(from, to)", script)
        self.assertIn("function redrawImageEditorBrushOverlay(ctx)", script)
        self.assertNotIn("function imageEditorPixelMatches(data, offset, target, tolerance)", script)
        self.assertNotIn("target = [", script)
        self.assertIn("function handleImageEditorHistoryShortcut(event)", script)
        self.assertIn("function isImageEditorModalOpen()", script)
        self.assertIn('if (!["select", "brush", "arrow", "crop", "fill", "eraser"].includes(tool)) return;', script)
        self.assertIn("function ensureImageEditorPromptHint()", script)
        self.assertIn("function imageEditorExportBlob(canvas)", script)
        self.assertIn("function editedUploadFilename(name)", script)
        self.assertIn("function isEditableImageSource(source)", script)
        self.assertIn("async function imageEditorSourceFile(source)", script)
        self.assertIn("async function remoteImageSourceFile(source)", script)
        self.assertIn('kind: "upload",', script)
        self.assertIn('legacyMethod("syncPromptGalleryMentionsFromInputs")', script)
        self.assertIn("if (imageEditorState.hasInstructionMarks) ensureImageEditorPromptHint();", script)
        self.assertIn("if (!source || !isEditableImageSource(source))", script)
        self.assertIn("hasInstructionMarks: imageEditorState.hasInstructionMarks", script)
        self.assertIn("canvasScope: imageEditorState.canvasScope", script)
        self.assertIn("imageEditorState.canvasScope = snapshot.canvasScope || \"base\";", script)
        self.assertIn("imageEditorState.hasInstructionMarks = Boolean(snapshot.hasInstructionMarks);", script)
        self.assertIn("imageEditorState.hasInstructionMarks = true;", script)
        self.assertIn('imageEditorState.tool = "crop";', script)
        self.assertNotIn('imageEditorState.tool = "brush";', script)
        self.assertIn('configureImageEditorStroke(ctx, { lineCap: "butt", lineJoin: "miter" })', script)
        self.assertIn("function imageEditorArrowGeometry(start, end, strokeWidthValue)", script)
        self.assertIn("const headWidth = Math.max(18, strokeWidth * 2.2);", script)
        self.assertIn("ctx.lineTo(geometry.shaftEnd.x, geometry.shaftEnd.y);", script)
        self.assertRegex(
            script,
            r"function drawEditorArrowOnContext\(ctx, start, end\)[\s\S]*ctx\.lineTo\(geometry\.shaftEnd\.x, geometry\.shaftEnd\.y\);[\s\S]*ctx\.stroke\(\);",
        )
        self.assertIn('els.imageEditorClose?.addEventListener("click", () => closeImageEditor())', script)
        self.assertIn('els.imageEditorCancel?.addEventListener("click", () => closeImageEditor())', script)
        self.assertIn('els.imageEditorSave?.addEventListener("click", saveImageEdit)', script)
        self.assertIn('els.imageEditorUndo?.addEventListener("click", undoImageEdit)', script)
        self.assertIn('els.imageEditorRedo?.addEventListener("click", redoImageEdit)', script)
        self.assertIn('els.imageEditorReset?.addEventListener("click", resetImageEdit)', script)
        self.assertIn('document.querySelectorAll<HTMLElement>("[data-image-editor-tool]")', script)
        self.assertIn('button.addEventListener("click", () => setImageEditorTool(button.dataset.imageEditorTool))', script)
        self.assertIn('document.querySelectorAll<HTMLElement>("[data-image-editor-color]")', script)
        self.assertIn('document.querySelectorAll<HTMLElement>("[data-image-editor-canvas-scope]")', script)
        self.assertIn("function setImageEditorCanvasScope(scope)", script)
        self.assertIn("fitImageEditorCanvasToLayers({ preserveCurrent: false, pushHistory: true, status: true });", script)
        self.assertIn("resetImageEditorCanvasToBase({ pushHistory: true, status: true });", script)
        self.assertIn('els.imageEditorColor?.addEventListener("input"', script)
        self.assertIn('els.imageEditorStroke?.addEventListener("input"', script)
        self.assertIn("addEventListener(\"pointerdown\", handleImageEditorPointerDown)", script)
        self.assertIn("addEventListener(\"pointermove\", handleImageEditorPointerMove)", script)
        self.assertIn("addEventListener(\"pointerup\", handleImageEditorPointerUp)", script)
        self.assertIn("addEventListener(\"pointercancel\", handleImageEditorPointerCancel)", script)
        self.assertIn('getTool() === "fill"', script)
        self.assertIn("drawEditorBrushBoundarySegment(from, to);", script)
        self.assertIn("drawEditorBrushOverlaySegment(from, to);", script)
        self.assertIn("redrawOverlay(ctx);", script)
        self.assertIn("imageEditorState.brushBoundaryCanvas", script)
        self.assertIn("imageEditorState.brushOverlayCanvas", script)
        self.assertIn("ctx.lineWidth = getBrushSettings().strokeWidth;", script)
        self.assertNotIn("imageEditorState.strokeWidth + 2", script)
        fill_source = Path("codex_image/webui/frontend/src/image-editor-fill.ts").read_text(encoding="utf-8")
        fill_client = Path("codex_image/webui/frontend/src/image-editor-fill-client.ts").read_text(encoding="utf-8")
        self.assertIn("if (!spans.length) return null;", fill_source)
        self.assertIn("if (left === 0 || right === width - 1 || row === 0 || row === height - 1) return null;", fill_source)
        self.assertIn('new Worker("/static/image-editor-fill-worker.js?v=1")', fill_client)
        self.assertIn("worker.terminate();", fill_client)
        self.assertIn('setImageEditorStatus(translate("imageEditor.closedRegionRequired"), "error");', script)
        self.assertIn("pushImageEditorHistory();", script)
        self.assertIn("event.metaKey || event.ctrlKey", script)
        self.assertIn('event.key.toLowerCase() === "z"', script)
        self.assertIn('event.key.toLowerCase() === "y"', script)
        self.assertIn("handleImageEditorHistoryShortcut(event)", script)
        self.assertRegex(script, r"function handleDocumentKeydown\(event\)\s*\{[\s\S]*event\.key === \"Escape\"[\s\S]*closeImageEditor\(\)")

    def test_input_image_editor_supports_layered_compositing(self) -> None:
        canvas_source = Path("codex_image/webui/frontend/src/image-editor-canvas.ts").read_text(encoding="utf-8")
        drawing_source = Path("codex_image/webui/frontend/src/image-editor-drawing.ts").read_text(encoding="utf-8")
        geometry_source = Path("codex_image/webui/frontend/src/image-editor-geometry.ts").read_text(encoding="utf-8")
        panel_source = Path("codex_image/webui/frontend/src/image-editor-panel.ts").read_text(encoding="utf-8")
        pointer_source = Path("codex_image/webui/frontend/src/image-editor-pointer.ts").read_text(encoding="utf-8")
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        image_editor_source = self._image_editor_source()

        self.assertIn('"konva"', Path("package.json").read_text(encoding="utf-8"))
        self.assertIn('id="imageEditorKonvaMount"', html)
        self.assertIn('id="imageEditorInsertList"', html)
        self.assertIn('id="imageEditorLayerList"', html)
        self.assertIn('id="imageEditorToolSelect"', html)
        self.assertIn('id="imageEditorToolEraser"', html)
        self.assertIn('id="imageEditorLayerUp"', html)
        self.assertIn('id="imageEditorLayerDown"', html)
        self.assertIn('id="imageEditorLayerDelete"', html)
        self.assertIn('class="image-editor-side-section image-editor-canvas-scope-section"', html)
        self.assertIn('data-image-editor-tool="select"', html)
        self.assertIn('data-image-editor-tool="eraser"', html)

        self.assertRegex(styles, r"\.image-editor-workspace\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+220px")
        self.assertRegex(styles, r"\.image-editor-side-panel\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.image-editor-konva-mount\s*\{[^}]*width:\s*var\(--image-editor-stage-width")
        self.assertRegex(styles, r"\.image-editor-konva-mount\s*\{[^}]*height:\s*var\(--image-editor-stage-height")
        self.assertRegex(
            styles,
            r"\.image-editor-konva-mount \.konvajs-content\s*\{[^}]*width:\s*var\(--image-editor-stage-raw-width",
        )
        self.assertRegex(
            styles,
            r"\.image-editor-konva-mount \.konvajs-content\s*\{[^}]*height:\s*var\(--image-editor-stage-raw-height",
        )
        self.assertRegex(styles, r"\.image-editor-konva-mount \.konvajs-content\s*\{[^}]*transform:\s*scale\(var\(--image-editor-stage-scale")
        self.assertRegex(styles, r"\.image-editor-konva-mount canvas\s*\{[^}]*width:\s*var\(--image-editor-stage-raw-width")
        self.assertRegex(styles, r"\.image-editor-konva-mount canvas\s*\{[^}]*height:\s*var\(--image-editor-stage-raw-height")
        self.assertNotRegex(styles, r"\.image-editor-konva-mount canvas\s*\{[^}]*width:\s*auto\s*!important")
        self.assertNotRegex(styles, r"\.image-editor-konva-mount canvas\s*\{[^}]*height:\s*auto\s*!important")
        self.assertRegex(styles, r"\.image-editor-layer-thumb img\s*\{[^}]*object-fit:\s*cover")

        self.assertIn("import Konva from \"konva\";", image_editor_source)
        self.assertIn("konvaStage: null", image_editor_source)
        self.assertIn("konvaLayer: null", image_editor_source)
        self.assertIn("konvaTransformer: null", image_editor_source)
        self.assertIn("let previewNode: Konva.Arrow | null = null", drawing_source)
        self.assertIn("layers: []", image_editor_source)
        self.assertIn("selectedLayerId: null", image_editor_source)
        self.assertIn('tool: "crop"', image_editor_source)
        self.assertIn("function renderImageEditorInsertList()", panel_source)
        self.assertIn("function renderImageEditorLayerList()", panel_source)
        self.assertIn("function imageEditorLayerThumbnailUrl(layer: ImageEditorLayer)", canvas_source)
        self.assertIn("const thumbnailUrl = imageEditorLayerThumbnailUrl(layer);", panel_source)
        self.assertIn("thumbnail.src = thumbnailUrl;", panel_source)
        self.assertIn("thumb.append(thumbnail);", panel_source)
        self.assertRegex(
            panel_source,
            r"if \(thumbnailUrl\) \{[\s\S]*thumb\.append\(thumbnail\);[\s\S]*\} else \{[\s\S]*thumb\.textContent = String\(getEditorSnapshot\(\)\.layers\.indexOf\(layer\) \+ 1\);",
        )
        self.assertRegex(image_editor_source, r"async function insertImageEditorLayerFromSource\(source(?::\s*any)?\)")
        self.assertRegex(image_editor_source, r"function selectImageEditorLayer\(layerId(?::\s*[^,)]+)?")
        self.assertRegex(
            image_editor_source,
            r"node\.on\(\"click tap\", \(event: any\) => \{[\s\S]*const point = imageEditorPoint\(event\.evt \|\| event\);[\s\S]*const hitLayer = imageEditorLayerAtPoint\(point\) \|\| layer;[\s\S]*selectImageEditorLayer\(hitLayer\.id, \{ updateTool: false \}\);",
        )
        self.assertRegex(
            image_editor_source,
            r"node\.on\(\"dragstart\", \(event: any\) => \{[\s\S]*const hitLayer = imageEditorLayerAtPoint\(point\) \|\| layer;[\s\S]*selectImageEditorLayer\(hitLayer\.id, \{ updateTool: false \}\);",
        )
        self.assertIn("function isImageEditorTransformerTarget(node: any)", image_editor_source)
        self.assertIn("current === imageEditorState.konvaTransformer", image_editor_source)
        self.assertIn("function imageEditorLayerAtPoint(point: any)", image_editor_source)
        self.assertIn("for (let index = imageEditorState.layers.length - 1; index >= 0; index -= 1)", image_editor_source)
        self.assertIn("function fitImageEditorCanvasToLayers", image_editor_source)
        self.assertIn("function resetImageEditorCanvasToBase", image_editor_source)
        self.assertIn("function resizeImageEditorCanvas", image_editor_source)
        self.assertIn("resizeImageEditorBackingCanvas(imageEditorState.workCanvas", image_editor_source)
        self.assertIn("if (imageEditorState.canvasScope === \"fit\")", image_editor_source)
        self.assertIn("fitImageEditorCanvasToLayers({ preserveCurrent: true });", image_editor_source)
        self.assertIn("const rect = layer.node.getClientRect?.({ skipShadow: true, skipStroke: true }) || layer.node.getClientRect?.() || null;", image_editor_source)
        self.assertRegex(image_editor_source, r"function moveImageEditorLayer\(direction(?::\s*any)?\)")
        self.assertIn("function deleteSelectedImageEditorLayer()", image_editor_source)
        self.assertIn("function imageEditorCompositeCanvas()", image_editor_source)
        self.assertRegex(drawing_source, r"function applyImageEditorLayerEraseStroke\(layer(?::\s*[^,]+)?, points(?::\s*any\[\])?\)")
        self.assertIn("function applyImageEditorLayerEraseSegment(layer: ImageEditorLayer, from: any, to: any)", drawing_source)
        self.assertIn("function applyImageEditorLayerEraseDot(layer: ImageEditorLayer, point: any)", drawing_source)
        self.assertIn("function imageEditorLayerCanvasPoint(layer: ImageEditorLayer, point: any)", drawing_source)
        self.assertIn("layer.canvas.width / Math.max(1, layer.node.width())", drawing_source)
        self.assertIn("layer.canvas.height / Math.max(1, layer.node.height())", drawing_source)
        self.assertIn("imageEditorLayerCanvasStrokeWidth(layer)", drawing_source)
        self.assertIn("drawing.changed = applyImageEditorLayerEraseSegment(layer, drawing.last, point) || drawing.changed;", pointer_source)
        self.assertIn("const changed = applyImageEditorLayerEraseDot(layer, point);", pointer_source)
        self.assertIn("new Konva.Arrow", drawing_source)
        self.assertIn('name: "image-editor-preview-arrow"', drawing_source)
        self.assertIn("function imageEditorArrowGeometry(start: any, end: any, strokeWidthValue: number)", geometry_source)
        self.assertIn("const headWidth = Math.max(18, strokeWidth * 2.2);", geometry_source)
        self.assertIn("ctx.lineTo(geometry.shaftEnd.x, geometry.shaftEnd.y);", drawing_source)
        self.assertRegex(
            drawing_source,
            r"function drawEditorArrowOnContext\(ctx: any, start: any, end: any\)[\s\S]*ctx\.lineTo\(geometry\.shaftEnd\.x, geometry\.shaftEnd\.y\);[\s\S]*ctx\.stroke\(\);",
        )
        self.assertIn("function clearImageEditorPreview()", drawing_source)
        self.assertIn("function updateImageEditorDisplayScale()", image_editor_source)
        self.assertIn("function updateImageEditorTransformerAffordance(displayScale: number)", image_editor_source)
        self.assertIn("transformer.anchorSize?.(Math.max(14, Math.round(14 / safeScale)))", image_editor_source)
        self.assertIn("transformer.rotateAnchorOffset?.(Math.max(28, Math.round(28 / safeScale)))", image_editor_source)
        self.assertIn("updateImageEditorTransformerAffordance(displayScale);", image_editor_source)
        self.assertIn('mount.style.setProperty("--image-editor-stage-width"', image_editor_source)
        self.assertIn('mount.style.setProperty("--image-editor-stage-height"', image_editor_source)
        self.assertIn('mount.style.setProperty("--image-editor-stage-raw-width"', image_editor_source)
        self.assertIn('mount.style.setProperty("--image-editor-stage-raw-height"', image_editor_source)
        self.assertIn('mount.style.setProperty("--image-editor-stage-scale"', image_editor_source)
        self.assertIn('"PointerEvent" in window', image_editor_source)
        self.assertIn('const downEvents = hasPointerEvents ? "pointerdown" : "mousedown touchstart";', image_editor_source)
        self.assertIn('const moveEvents = hasPointerEvents ? "pointermove" : "mousemove touchmove";', image_editor_source)
        self.assertIn('const upEvents = hasPointerEvents ? "pointerup pointercancel" : "mouseup touchend";', image_editor_source)
        self.assertIn("stage.setPointersPositions?.(event);", image_editor_source)
        self.assertIn('const target = mount?.querySelector(".konvajs-content") || mount || canvas;', image_editor_source)
        self.assertIn("const scaleX = stageWidth / Math.max(1, rect.width);", image_editor_source)
        self.assertIn("const scaleY = stageHeight / Math.max(1, rect.height);", image_editor_source)
        self.assertIn("Math.min(stageWidth, (event.clientX - rect.left) * scaleX)", image_editor_source)
        self.assertIn("captureImageEditorPointer(event)", pointer_source)
        self.assertRegex(
            image_editor_source,
            r"if \(imageEditorState\.tool === \"select\"\) \{[\s\S]*if \(isImageEditorTransformerTarget\(event\.target\)\) return;[\s\S]*if \(event\.target === stage\) selectImageEditorLayer\(null, \{ updateTool: false \}\);[\s\S]*return;",
        )
        self.assertIn("new Konva.Transformer", image_editor_source)
        self.assertIn("keepRatio: true", image_editor_source)
        self.assertIn('shiftBehavior: "inverted"', image_editor_source)
        self.assertIn("anchorSize: 14", image_editor_source)
        self.assertIn('anchorStroke: "#2F6FE4"', image_editor_source)
        self.assertIn('anchorFill: "#FFFFFF"', image_editor_source)
        self.assertIn('borderStroke: "#2F6FE4"', image_editor_source)
        self.assertIn("rotateAnchorOffset: 28", image_editor_source)
        self.assertIn("imageEditorState.konvaTransformer?.moveToTop?.();", image_editor_source)
        self.assertIn("new Konva.Image", image_editor_source)
        self.assertIn("globalCompositeOperation = \"destination-out\"", drawing_source)
        self.assertIn('if (!["select", "brush", "arrow", "crop", "fill", "eraser"].includes(tool)) return;', script)
        self.assertRegex(script, r"function resetForm\(\)\s*\{[\s\S]*closeGallery\(\);[\s\S]*closeImageEditor\(\);")
        self.assertIn("openImageEditor(index)", script)
        self.assertIn("editable-thumb", script)
        self.assertNotIn('className = "thumb-edit"', script)
        self.assertIn("thumb-edited-badge", script)
        self.assertNotRegex(
            script,
            r'if \(source\.kind === "upload"\) \{[\s\S]*const edit = document\.createElement\("button"\)',
        )
        self.assertIn('form.append("reference_images", source.file)', script)
        self.assertIn('form.append("images", source.file)', script)
    def test_theme_mode_markup_and_bootstrap_exist(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")

        self.assertRegex(html, r"<script>\s*\(\(\) => \{[\s\S]*THEME_STORAGE_KEY")
        self.assertRegex(html, r"document\.documentElement\.dataset\.theme =")
        self.assertRegex(html, r"<script>[\s\S]*</script>\s*<link rel=\"stylesheet\"")
        self.assertIn('id="themeSwitcher"', html)
        self.assertIn('data-theme-option="system"', html)
        self.assertIn('data-theme-option="light"', html)
        self.assertIn('data-theme-option="dark"', html)
        self.assertIn('aria-label="主题模式"', html)
    def test_theme_mode_javascript_and_styles_exist(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        theme_source = Path(
            "codex_image/webui/frontend/src/theme-preference.ts"
        ).read_text(encoding="utf-8")
        shell_source = Path(
            "codex_image/webui/frontend/src/shell-ui.ts"
        ).read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('"codex-image-theme-preference"', theme_source)
        self.assertIn('themePreference: "system"', script)
        self.assertIn('call(methods, "restoreThemePreference")', script)
        self.assertIn('from "./theme-preference";', shell_source)
        self.assertIn("function resolveEffectiveTheme", shell_source)
        self.assertIn("function applyThemePreference", shell_source)
        self.assertIn("function updateThemeSwitcher", shell_source)
        self.assertIn("function handleThemeSystemChange", shell_source)
        self.assertIn("let themeTransitionFrame", theme_source)
        self.assertIn("function lockThemeTransitions", theme_source)
        self.assertIn('root.classList.add("theme-transition-lock")', theme_source)
        self.assertIn('root.classList.remove("theme-transition-lock")', theme_source)
        self.assertRegex(
            theme_source,
            r"function applyDocumentTheme\([\s\S]*lockThemeTransitions\(root\)",
        )
        self.assertIn("storage.getItem(THEME_STORAGE_KEY)", theme_source)
        self.assertIn("storage.setItem(THEME_STORAGE_KEY", theme_source)
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\]\s*\{[\s\S]*--bg:")
        self.assertIn("--success-soft:", styles)
        self.assertIn("--danger-soft:", styles)
        self.assertLess(styles.index("--danger-soft:"), styles.index("var(--danger-soft)"))
        self.assertRegex(styles, r"\.theme-switcher\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.theme-switcher\s*\{[^}]*height:\s*var\(--top-nav-control-height\)")
        self.assertRegex(styles, r"\.theme-switcher\s*\{[^}]*border-radius:\s*var\(--top-nav-control-radius\)")
        self.assertRegex(styles, r"\.theme-option\s*\{[^}]*height:\s*var\(--top-nav-segment-height\)")
        self.assertRegex(styles, r"\.theme-option\s*\{[^}]*border-radius:\s*var\(--top-nav-control-radius\)")
        self.assertRegex(styles, r"\.theme-option\.active\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(
            styles,
            r":root\.theme-transition-lock \*,\s*:root\.theme-transition-lock \*::before,\s*:root\.theme-transition-lock \*::after\s*\{[^}]*transition:\s*none !important",
        )
    def test_dark_theme_primary_controls_use_contrast_foreground(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("--primary-foreground:", styles)
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\]\s*\{[\s\S]*--primary-foreground:\s*#10201b;")
        for selector in (
            ".primary-button",
            ".run-button",
            ".theme-option.active",
            ".auth-source-button.active",
            ".system-settings-tab.active",
            ".system-settings-tabs.segmented-indicator-host .system-settings-tab.active",
            ".radio-btn.active",
            ".quick-gallery-category.active",
            ".resource-manage-button",
            ".prompt-copy-button",
            ".image-editor-tool.active",
        ):
            with self.subTest(selector=selector):
                self.assertRegex(
                    styles,
                    rf"{re.escape(selector)}\s*\{{[^}}]*color:\s*var\(--primary-foreground\)",
                )

        provider_active = self._extract_css_block(styles, ".api-provider-choice.active")
        provider_meta = self._extract_css_block(styles, ".api-provider-choice.active span")
        self.assertIn("background: var(--primary-light)", provider_active)
        self.assertIn("color: var(--text)", provider_active)
        self.assertIn("color: var(--text-secondary)", provider_meta)
        self.assertNotIn("var(--primary-foreground)", provider_active)
        self.assertNotIn("var(--primary-foreground)", provider_meta)

        for selector in (
            ".primary-button",
            ".run-button",
            ".segment.active",
            ".radio-btn.active",
            ".auth-source-button.active",
            ".system-settings-tab.active",
            ".system-settings-tabs.segmented-indicator-host .system-settings-tab.active",
            ".api-provider-choice.active",
        ):
            with self.subTest(selector=selector):
                self.assertNotRegex(
                    styles,
                    rf"{re.escape(selector)}\s*\{{[^}}]*color:\s*(white|#fff)",
                )
    def test_dark_theme_image_input_and_gallery_use_theme_surfaces(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        image_input_block = self._extract_css_block(styles, ".image-input-main")
        quick_center_block = self._extract_css_block(styles, ".quick-gallery-item.center")
        quick_hover_block = self._extract_css_block(styles, ".quick-gallery-item:hover,\n.quick-gallery-item.active")

        self.assertIn("color-mix(in srgb, var(--surface-soft)", image_input_block)
        self.assertNotIn("rgba(255,255,255", image_input_block)
        self.assertNotIn("rgba(237, 246, 242", image_input_block)
        self.assertIn("var(--primary-light)", quick_center_block)
        self.assertIn("var(--primary-light)", quick_hover_block)
        self.assertNotIn("rgba(231, 242, 237", quick_center_block)
        self.assertNotIn("rgba(248, 251, 249", quick_hover_block)
    def test_dark_theme_panels_and_titles_use_soft_visual_hierarchy(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        panel_block = self._extract_css_block(styles, ".panel")
        panel_heading_block = self._extract_css_block(styles, ".panel h2")
        task_title_block = self._extract_css_block(styles, ".task-title")

        self.assertIn("--panel-border:", styles)
        self.assertIn("--section-heading:", styles)
        self.assertIn("--task-title:", styles)
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\]\s*\{[\s\S]*--panel-border:\s*color-mix\(in srgb, var\(--line\) 58%, transparent\);")
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\]\s*\{[\s\S]*--section-heading:\s*color-mix\(in srgb, var\(--text\) 58%, var\(--text-secondary\)\);")
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\]\s*\{[\s\S]*--task-title:\s*color-mix\(in srgb, var\(--text\) 36%, var\(--text-secondary\)\);")
        self.assertIn("border: 1px solid var(--panel-border)", panel_block)
        self.assertRegex(styles, r"\.modal-panel\s*\{[^}]*width:\s*min\(920px,\s*94vw\)[^}]*border:\s*1px solid var\(--panel-border\)")
        self.assertRegex(styles, r"\.queue-drawer\s*\{[^}]*border-left:\s*1px solid var\(--panel-border\)")
        self.assertIn("color: var(--section-heading)", panel_heading_block)
        self.assertIn("color: var(--task-title)", task_title_block)
        self.assertNotIn("rgba(226, 232, 229", panel_block)
        self.assertNotRegex(styles, r"\.modal-panel\s*\{[^}]*width:\s*min\(920px,\s*94vw\)[^}]*rgba\(226, 232, 229")
        self.assertNotIn("rgba(226, 232, 229", styles)
