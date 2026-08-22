"""
tools/declarations.py — Gemini-Live Tool-Schema (TOOL_DECLARATIONS).

Ausgelagert aus main.py (P1 Refactoring-Plan #4). Reine Datenstruktur,
keine main.py-Ballast mehr - main.py importiert diese Liste nur noch.
Verhalten unveraendert: identischer Inhalt wie zuvor in main.py.
"""

TOOL_DECLARATIONS = [
    {
        "name": "window_manager",
        "description": (
            "Manages open windows on the PC: list all open windows, bring a window "
            "to the front (focus), minimize, maximize, close, minimize everything, "
            "or arrange two windows side by side. Use when the user talks about "
            "windows, e.g. 'fokussiere Chrome', 'minimiere alles', "
            "'zeig Chrome und Word nebeneinander'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":        {"type": "STRING", "description": "list | focus | minimize | maximize | close | minimize_all | side_by_side"},
                "window_title":  {"type": "STRING", "description": "Part of the window title, e.g. 'Chrome'"},
                "second_window": {"type": "STRING", "description": "Second window title (only for side_by_side)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "smart_search",
        "description": (
            "Deep file search that looks INSIDE file contents, not just filenames. "
            "Searches Documents, Desktop and Downloads. Use when the user is looking "
            "for a file by topic or content, e.g. 'such die Datei ueber die "
            "Steuererklaerung', 'finde meine Notizen zum Projekt X'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "What to search for (topic, keywords)"},
                "folder": {"type": "STRING", "description": "Optional: specific folder path to search in"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "adaptive_brightness",
        "description": (
            "Starts or stops adaptive screen brightness: the webcam measures ambient "
            "light and the screen brightness follows it smoothly (dark room = dimmer, "
            "bright room = brighter). Use when the user asks for automatic/adaptive "
            "brightness."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "start | stop | status"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "app_volume",
        "description": (
            "Controls the volume of INDIVIDUAL applications (per-app volume mixer), "
            "like the Windows volume mixer. Use when the user wants to change, mute, "
            "or unmute the volume of a specific program (e.g. 'set Spotify to 30 percent', "
            "'mute Chrome') or asks which apps are currently playing audio. "
            "NOT for the global system volume."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING", "description": "list | set | mute | unmute"},
                "app_name": {"type": "STRING", "description": "Application name, e.g. 'Spotify', 'Chrome'"},
                "level":    {"type": "NUMBER", "description": "Target volume 0-100 (only for action=set)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "gesture_control",
        "description": (
            "Starts or stops Rencora-style hand gesture control via webcam: the user "
            "moves the mouse cursor with their index finger and clicks by pinching "
            "thumb and index finger together. Use when the user asks to control the "
            "PC with hand gestures / 'Gestensteuerung'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "start | stop | status"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) | compare | news | research | price"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use browser_control or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "calendar_mail",
        "description": (
            "Manages calendar events and email. Use for: checking today's "
            "schedule, upcoming events, creating/moving/cancelling calendar "
            "events, reading or summarizing recent emails, checking unread "
            "or important mail. ONLY tool for calendar and email requests."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": (
                    "agenda_today | agenda_range | create_event | move_event | "
                    "cancel_event | list_unread_mail | summarize_mail | search_mail"
                )},
                "title":        {"type": "STRING", "description": "Event title / mail search query"},
                "date":         {"type": "STRING", "description": "Date YYYY-MM-DD"},
                "time":         {"type": "STRING", "description": "Time HH:MM (24h)"},
                "duration_min": {"type": "INTEGER", "description": "Event duration in minutes (default 60)"},
                "days_ahead":   {"type": "INTEGER", "description": "How many days ahead for agenda_range"},
                "event_id":     {"type": "STRING", "description": "Event id for move_event/cancel_event"},
                "max_results":  {"type": "INTEGER", "description": "Max emails to return (default 5)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "second_brain_save",
        "description": (
            "Processes an uploaded file and permanently files it into the "
            "user's Second Brain (a personal knowledge base): extracts the "
            "content (text/image/PDF/audio/etc.), generates a summary and "
            "key facts, and stores it so it can be found later. ALWAYS call "
            "this when a file was uploaded specifically to the Second Brain "
            "(marked as such), or when the user explicitly asks to save/file "
            "something into their Second Brain / permanent notes."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_path": {"type": "STRING", "description": "Full path to the uploaded file."},
                "note":      {"type": "STRING", "description": "Optional short user note/context about why this was saved."},
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "second_brain_recall",
        "description": (
            "Searches the user's Second Brain (previously filed documents, "
            "notes, screenshots, receipts, etc.) for a topic or keyword and "
            "returns matching summaries and key facts. Use when the user "
            "asks about something they saved/filed/dropped in earlier, or "
            "asks 'what did I save about X'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Topic or keyword to search for"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "system_status",
        "description": (
            "Reports current system metrics: CPU load, RAM usage, CPU "
            "temperature, GPU load, uptime, process count. Use when the "
            "user asks how the PC is doing, how hot it is, how much RAM "
            "is used, or similar system-health questions."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Plans and executes multi-step everyday tasks that need more "
            "than one tool call (e.g. researching something AND messaging "
            "someone about it, or checking the calendar AND sending an "
            "invite). ONLY for complex, multi-step requests (3+ steps) "
            "that genuinely span multiple tools. Do not call this when a "
            "single existing tool can accomplish the request."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal": {"type": "STRING", "description": "What the user ultimately wants accomplished, in their own words"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "task_manager",
        "description": (
            "Manages the user's persistent to-do and automation list "
            "(tasks, subtasks, priorities, dependencies, recurrence). Use "
            "when the user wants to remember, plan, track, update, complete "
            "or drop concrete tasks ('add a task ...', 'what's on my list', "
            "'mark task 3 done', 'break this into steps'). Tasks survive "
            "restarts. For a single time-based alarm use 'reminder' instead."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING", "enum": ["create", "list", "update", "complete", "delete"], "description": "What to do"},
                "id":         {"type": "INTEGER", "description": "Task id (for update/complete/delete)"},
                "title":      {"type": "STRING", "description": "Task title (for create/update)"},
                "details":    {"type": "STRING", "description": "Optional longer description"},
                "priority":   {"type": "INTEGER", "description": "0 low, 1 normal, 2 high, 3 urgent"},
                "parent_id":  {"type": "INTEGER", "description": "Parent task id to make this a subtask"},
                "depends_on": {"type": "INTEGER", "description": "Id of a task that must finish first"},
                "status":     {"type": "STRING", "enum": ["pending", "active", "blocked", "done", "cancelled"], "description": "New status (for update)"},
                "due_at":     {"type": "STRING", "description": "Optional due date/time (ISO or plain text)"},
                "recurrence": {"type": "STRING", "description": "Optional 'daily' or 'weekly' for recurring tasks"},
                "include_done": {"type": "BOOLEAN", "description": "For list: include completed tasks"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "shutdown_rencora",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop RENCORA. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "import_whatsapp_chat",
        "description": (
            "Imports a WhatsApp chat export (.txt file) and stores EVERY message "
            "each person sent — verbatim, in full, nothing filtered or summarized "
            "away, no matter how small or trivial. Also generates a short recap per "
            "person for quick reference. ALWAYS call this when the user uploads a "
            ".txt file that looks like a WhatsApp chat export (lines starting with "
            "dates/times and a sender name), or when the user explicitly asks to "
            "import/remember a WhatsApp chat."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_path": {
                    "type": "STRING",
                    "description": "Full path to the uploaded .txt chat export. Leave empty to use the currently uploaded file."
                },
                "me_name": {
                    "type": "STRING",
                    "description": "The user's own display name in the chat, if known, so their own messages are excluded from the analysis."
                }
            },
            "required": []
        }
    },
    {
        "name": "recall_person_chat",
        "description": (
            "Looks up the full, verbatim WhatsApp message history stored for one "
            "specific person (imported earlier via import_whatsapp_chat). Use this "
            "when the short recap in your context isn't enough and you need an exact "
            "detail, quote, or something small the person mentioned — dates, "
            "specific wording, a one-off comment, etc."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name":  {"type": "STRING", "description": "The person's name as known in memory."},
                "query": {"type": "STRING", "description": "Optional keyword to filter their messages by (e.g. 'birthday', 'Berlin')."},
                "limit": {"type": "INTEGER", "description": "Max messages to return (default 40, max 200)."}
            },
            "required": ["name"]
        }
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Sebastian, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
]
