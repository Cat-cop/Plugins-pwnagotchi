import logging
import os
import time
import re
import textwrap
import json

from flask import render_template_string
import pwnagotchi.plugins as plugins

LOG = logging.getLogger(__name__)

# Default values
DEFAULT_INTERVAL = 4.0
DEFAULT_MAX_CHARS = 16
DEFAULT_MAX_LINES = 3
DEFAULT_INDENT = 0

SETTINGS_PATH = "/var/tmp/pwnagotchi_tmp_message.json"

TEMPLATE = """
{% extends "base.html" %}
{% set active_page = "tmp_message" %}

{% block title %}Tmp Message{% endblock %}

{% block content %}
  <h1>Tmp Message Plugin</h1>

  <p style="font-size:12px;color:#777;margin-top:-4px;">
    Author: KittyOWL
  </p>

  <form method="POST">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

    <label style="display:inline-flex;align-items:center;gap:5px;margin:10px 0;">
      <input type="checkbox" name="enabled" {% if enabled %}checked{% endif %}>
      Enable plugin (allow showing on screen)
    </label>
    <br><br>

    <label>
      Chars per line:
      <input type="number" name="width" value="{{ max_width }}" min="5" max="32"
             style="width:60px;">
    </label>
    &nbsp;&nbsp;
    <label>
      Lines per chunk:
      <input type="number" name="lines" value="{{ max_lines }}" min="1" max="5"
             style="width:60px;">
    </label>
    &nbsp;&nbsp;
    <label>
      Interval (sec):
      <input type="number" step="0.5" name="interval" value="{{ interval }}" min="1" max="60"
             style="width:80px;">
    </label>
    &nbsp;&nbsp;
    <label>
      Indent (spaces):
      <input type="number" name="indent" value="{{ indent }}" min="0" max="10"
             style="width:60px;">
    </label>

    <br><br>

    <textarea name="message"
              style="width:100%;height:150px;box-sizing:border-box;background:#222;
                     color:#eee;border:1px solid #555;padding:8px;font-family:monospace;">{{ current_text }}</textarea>
    <br><br>

    <button type="submit" name="action" value="save"
            style="padding:6px 12px;border:1px solid #555;background:#333;color:#eee;cursor:pointer;">
      Save (update & preview)
    </button>

    <button type="submit" name="action" value="send"
            style="padding:6px 12px;border:1px solid #555;background:#333;color:#eee;cursor:pointer;margin-left:8px;">
      Send to screen
    </button>

    <button type="submit" name="action" value="stop"
            style="padding:6px 12px;border:1px solid #555;background:#533;color:#eee;cursor:pointer;margin-left:8px;">
      Stop scrolling
    </button>
  </form>

  <div style="margin-top:15px;font-size:12px;color:#aaa;">
    File: {{ file_path }}<br>
    Position: {{ position }}<br>
    Max: {{ max_lines }} lines × {{ max_width }} chars, interval {{ interval }}s<br>
    Indent: {{ indent }} spaces<br>
    Settings stored in: {{ settings_path }}
  </div>

  {% if status %}
    <div style="margin-top:10px;color:#0f0;">
      {{ status }}
    </div>
  {% endif %}

  {% if sent %}
    <div style="margin-top:5px;color:#0f0;font-size:12px;">
      Scrolling is ACTIVE: chunks are shown on screen.
    </div>
  {% else %}
    <div style="margin-top:5px;color:#f5a623;font-size:12px;">
      Scrolling is NOT active. Press "Send to screen" to start.
    </div>
  {% endif %}

  {% if preview_chunks %}
    <h2 style="margin-top:20px;font-size:16px;">Preview chunks (how it will look)</h2>
    {% for ch in preview_chunks %}
      <pre style="background:#111;border:1px solid #444;padding:6px;margin:4px 0;
                  display:inline-block;min-width:{{ max_width }}ch;white-space:pre;
                  color:#eee;font-family:monospace;">
{{ ch }}</pre>
    {% endfor %}
  {% endif %}

  <p style="margin-top:20px;font-size:11px;color:#888;">
    Small note from the author: this plugin code was written with the help of ChatGPT,
    because I am still learning how to code. Sorry for writing a whole plugin with AI
    instead of learning how to code :3
  </p>
{% endblock %}
"""


class TmpMessage(plugins.Plugin):
    __author__ = "b6931629ed768962a419614d51eede1fbd272bb035bb51d15b74536b9921ef7c"
    __version__ = "1.7.0"
    __license__ = "GPL3" #idk lol
    __description__ = (
        "Custom scrolling message plugin for Pwnagotchi. "
        "Remember evry time you reboot, message delete. "
        "Shows long text in chunks on the display. "
        "Written with the help of ChatGPT because the author is lazy to learn code."
    )

    def __init__(self):
        super().__init__()
        self.enabled = False
        self.file_path = "/tmp/pwnagotchi_msg.txt"
        self.position = "bottom"  # bottom | name | custom key

        # Rendering / timing settings
        self.display_interval = DEFAULT_INTERVAL
        self.max_chars_per_line = DEFAULT_MAX_CHARS
        self.max_lines_per_chunk = DEFAULT_MAX_LINES
        self.indent_spaces = DEFAULT_INDENT

        # Scrolling state
        self.sent = False
        self._chunks = []
        self._index = 0
        self._last_update = 0.0

    # ---------- settings persistence ----------
    def _load_settings_file(self):
        """Load persistent settings (width, lines, interval, indent) from disk."""
        if not os.path.exists(SETTINGS_PATH):
            return
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.max_chars_per_line = int(data.get("width", self.max_chars_per_line))
            self.max_lines_per_chunk = int(data.get("lines", self.max_lines_per_chunk))
            self.display_interval = float(data.get("interval", self.display_interval))
            self.indent_spaces = int(data.get("indent", self.indent_spaces))
            LOG.info(
                "[tmp_message] Settings loaded from %s: width=%d lines=%d interval=%.1f indent=%d",
                SETTINGS_PATH,
                self.max_chars_per_line,
                self.max_lines_per_chunk,
                self.display_interval,
                self.indent_spaces,
            )
        except Exception as e:
            LOG.error("[tmp_message] Failed to load settings %s: %s", SETTINGS_PATH, e)

    def _save_settings_file(self):
        """Save current settings (width, lines, interval, indent) to disk."""
        data = {
            "width": self.max_chars_per_line,
            "lines": self.max_lines_per_chunk,
            "interval": self.display_interval,
            "indent": self.indent_spaces,
        }
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f)
            LOG.info(
                "[tmp_message] Settings saved to %s: width=%d lines=%d interval=%.1f indent=%d",
                SETTINGS_PATH,
                self.max_chars_per_line,
                self.max_lines_per_chunk,
                self.display_interval,
                self.indent_spaces,
            )
        except Exception as e:
            LOG.error("[tmp_message] Failed to save settings %s: %s", SETTINGS_PATH, e)

    # ---------- plugin lifecycle ----------
    def on_loaded(self):
        """Called by Pwnagotchi when the plugin is loaded."""
        cfg = self.options or {}

        self.enabled = bool(cfg.get("enabled", False))
        self.file_path = cfg.get("file_path", self.file_path)
        self.position = cfg.get("position", self.position)

        # Optional defaults from config.toml
        self.max_chars_per_line = int(cfg.get("width", self.max_chars_per_line))
        self.max_lines_per_chunk = int(cfg.get("lines", self.max_lines_per_chunk))
        self.display_interval = float(cfg.get("interval", self.display_interval))
        self.indent_spaces = int(cfg.get("indent", self.indent_spaces))

        # Override with persistent settings, if present
        self._load_settings_file()

        self.sent = False
        self._chunks = []
        self._index = 0
        self._last_update = 0.0

        LOG.info(
            "[tmp_message] Loaded. enabled=%s file_path=%s position=%s width=%d lines=%d interval=%.1f indent=%d",
            self.enabled,
            self.file_path,
            self.position,
            self.max_chars_per_line,
            self.max_lines_per_chunk,
            self.display_interval,
            self.indent_spaces,
        )

    # ---------- text splitting / wrapping ----------
    def _effective_width(self) -> int:
        """Return the width available for text after applying left indent."""
        return max(1, self.max_chars_per_line - max(0, self.indent_spaces))

    def _split_long_word(self, word: str):
        """Split a single long word so it fits into the effective line width."""
        width = self._effective_width()
        if len(word) <= width:
            return [word]
        parts = []
        start = 0
        while start < len(word):
            parts.append(word[start : start + width])
            start += width
        return parts

    def _build_chunks(self, text: str):
        """
        Convert raw text into a list of chunks:
        - normalize newlines and paragraphs;
        - wrap to effective width;
        - limit number of lines per chunk;
        - add left indent to every line.
        """
        text = text.replace("\r", "\n").strip()
        if not text:
            return []

        # Split into "paragraphs" separated by blank lines
        paragraphs = re.split(r"\n\s*\n", text)
        all_words = []

        for para in paragraphs:
            normalized = re.sub(r"\s+", " ", para.strip())
            if not normalized:
                continue
            all_words.append("\nPARA_BREAK\n")
            all_words.extend(normalized.split(" "))

        # Remove leading paragraph marker if present
        if all_words and all_words[0] == "\nPARA_BREAK\n":
            all_words = all_words[1:]

        # Split too-long words
        words = []
        for w in all_words:
            if w == "\nPARA_BREAK\n":
                words.append(w)
            else:
                words.extend(self._split_long_word(w))

        chunks = []
        current_words = []
        indent_str = " " * max(0, self.indent_spaces)
        width = self._effective_width()
        max_lines = max(1, self.max_lines_per_chunk)
        target_chars = max(1, width * max_lines)

        def flush_current():
            """Finalize current buffer into one or more chunks."""
            if not current_words:
                return
            sentence = " ".join(w for w in current_words if w != "\nPARA_BREAK\n").strip()
            if not sentence:
                current_words.clear()
                return

            lines = textwrap.wrap(sentence, width=width)
            if not lines:
                current_words.clear()
                return

            while lines:
                part_lines = lines[:max_lines]
                lines = lines[max_lines:]
                chunks.append("\n".join(indent_str + line for line in part_lines))

            current_words.clear()

        for w in words:
            if w == "\nPARA_BREAK\n":
                flush_current()
                continue

            if not current_words:
                current_words.append(w)
                continue

            candidate = " ".join(x for x in (current_words + [w]) if x != "\nPARA_BREAK\n")
            if len(candidate) > target_chars:
                flush_current()
                current_words.append(w)
            else:
                current_words.append(w)

        flush_current()
        return chunks

    # ---------- UI update ----------
    def on_ui_update(self, ui):
        """Called by Pwnagotchi UI loop; updates the screen text when needed."""
        if not (self.enabled and self.sent and self._chunks):
            return

        now = time.time()
        if self._last_update == 0.0:
            self._last_update = now
        else:
            if now - self._last_update >= self.display_interval:
                self._index = (self._index + 1) % len(self._chunks)
                self._last_update = now

        chunk = self._chunks[self._index]

        if self.position == "bottom":
            ui.set("status", chunk)
        elif self.position == "name":
            ui.set("name", chunk)
        else:
            ui.set(self.position, chunk)

    # ---------- web UI ----------
    def on_webhook(self, path, request):
        """
        Handle web requests under /plugins/tmp_message.
        - GET  -> show current config and preview
        - POST -> save message/settings, optionally start/stop scrolling
        """
        if path not in (None, "", "/"):
            return None

        # Load currently stored message for the textarea
        current_text = ""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    current_text = f.read()
            except Exception as e:
                LOG.error("[tmp_message] Error reading %s: %s", self.file_path, e)

        status = ""
        preview_chunks = self._chunks[:] if self._chunks else []

        if request.method == "POST":
            form = request.form
            message = form.get("message", "")
            enabled_flag = form.get("enabled")
            action = form.get("action", "save")

            self.enabled = bool(enabled_flag)

            def parse_int(val, default, min_v, max_v):
                try:
                    v = int(val)
                    return max(min_v, min(max_v, v))
                except Exception:
                    return default

            def parse_float(val, default, min_v, max_v):
                try:
                    v = float(val)
                    return max(min_v, min(max_v, v))
                except Exception:
                    return default

            # Parse and clamp numeric settings
            self.max_chars_per_line = parse_int(
                form.get("width", self.max_chars_per_line),
                self.max_chars_per_line,
                5,
                32,
            )
            self.max_lines_per_chunk = parse_int(
                form.get("lines", self.max_lines_per_chunk),
                self.max_lines_per_chunk,
                1,
                5,
            )
            max_indent = max(0, self.max_chars_per_line - 1)
            self.indent_spaces = parse_int(
                form.get("indent", self.indent_spaces),
                self.indent_spaces,
                0,
                max_indent,
            )
            self.display_interval = parse_float(
                form.get("interval", self.display_interval),
                self.display_interval,
                1.0,
                60.0,
            )

            # Persist settings to disk
            self._save_settings_file()

            try:
                # Save message to file
                with open(self.file_path, "w", encoding="utf-8") as f:
                    f.write(message)
                current_text = message

                # Rebuild chunks for preview / display
                new_chunks = self._build_chunks(message)
                preview_chunks = new_chunks

                if action == "send":
                    # Start scrolling on screen
                    self._chunks = new_chunks
                    self._index = 0
                    self._last_update = 0.0
                    self.sent = bool(self._chunks)
                    status = (
                        "Saved and scrolling on screen."
                        if self.sent
                        else "Nothing to show (empty text)."
                    )
                elif action == "stop":
                    # Stop scrolling but keep preview and text
                    self._chunks = new_chunks
                    self._index = 0
                    self._last_update = 0.0
                    self.sent = False
                    status = "Scrolling stopped. Preview updated."
                else:  # "save"
                    # Only update preview and stored text
                    self._chunks = new_chunks
                    self._index = 0
                    self._last_update = 0.0
                    self.sent = False
                    status = "Saved. Preview updated (scrolling is OFF)."

                LOG.info(
                    "[tmp_message] action=%s chunks=%d enabled=%s width=%d lines=%d interval=%.1f indent=%d",
                    action,
                    len(self._chunks),
                    self.enabled,
                    self.max_chars_per_line,
                    self.max_lines_per_chunk,
                    self.display_interval,
                    self.indent_spaces,
                )

            except Exception as e:
                status = "Error while saving: %s" % e
                LOG.error("[tmp_message] Error writing %s: %s", self.file_path, e)

        return render_template_string(
            TEMPLATE,
            current_text=current_text,
            enabled=self.enabled,
            sent=self.sent,
            status=status,
            file_path=self.file_path,
            position=self.position,
            interval=self.display_interval,
            max_width=self.max_chars_per_line,
            max_lines=self.max_lines_per_chunk,
            preview_chunks=preview_chunks,
            settings_path=SETTINGS_PATH,
            indent=self.indent_spaces,
            author=self.__author__,
        )
