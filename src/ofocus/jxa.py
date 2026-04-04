"""JXA bridge and JavaScript snippet constants."""

import json
import subprocess
from typing import Any

from ofocus.omni import OmniError

# ── JS snippet building blocks ──────────────────────────────────────────

JS_LOCAL_DATE_HELPERS = """\
function toLocalDateString(d) {
    if (!d) return null;
    var year = d.getFullYear();
    var month = String(d.getMonth() + 1).padStart(2, "0");
    var day = String(d.getDate()).padStart(2, "0");
    return year + "-" + month + "-" + day;
}
"""

JS_ACTION_TASK_HELPERS = """\
function isIndividualAction(t) {
    var parent = t.parentTask();
    return parent && t.tasks().length === 0;
}
"""

# Reusable JXA function: fuzzy-match an item from a list by ID or name.
# Returns {match: item} on unique match, {error: "ambiguous", matches: [...]}
# on multiple, or {error: "not_found"} on none.
JS_FUZZY_MATCH = """\
function fuzzyMatch(items, query) {
    var i;
    // Exact ID
    for (i = 0; i < items.length; i++) {
        if (items[i].id() === query) return {match: items[i]};
    }
    // ID prefix
    var prefixes = [];
    for (i = 0; i < items.length; i++) {
        if (items[i].id().indexOf(query) === 0) prefixes.push(items[i]);
    }
    if (prefixes.length === 1) return {match: prefixes[0]};
    if (prefixes.length > 1) return {
        error: "ambiguous",
        matches: prefixes.map(function(x) { return {id: x.id(), name: x.name()}; })
    };
    // Name substring (case-insensitive)
    var lq = query.toLowerCase();
    var names = [];
    for (i = 0; i < items.length; i++) {
        if (items[i].name().toLowerCase().indexOf(lq) !== -1) names.push(items[i]);
    }
    if (names.length === 1) return {match: names[0]};
    if (names.length > 1) return {
        error: "ambiguous",
        matches: names.map(function(x) { return {id: x.id(), name: x.name()}; })
    };
    return {error: "not_found"};
}
"""

# Reusable JXA function: resolve a task by exact ID or unique ID prefix.
# Returns {match: task} on unique match, {error: "ambiguous", matches: [...]}
# on multiple, or {error: "Task not found"} on none.
JS_FIND_TASK_BY_ID = """\
function findTaskById(doc, query) {
    var all = doc.flattenedTasks();
    var matches = all.filter(function(t) {
        return t.id() === query;
    });
    if (matches.length === 0) {
        matches = all.filter(function(t) {
            return t.id().indexOf(query) === 0;
        });
    }
    if (matches.length === 0) {
        return {error: "Task not found"};
    }
    if (matches.length > 1) {
        return {
            error: "ambiguous",
            matches: matches.map(function(t) {
                return {id: t.id(), name: t.name()};
            })
        };
    }
    return {match: matches[0]};
}
"""

JS_PROJECT_LIST_HELPERS = """\
function getProjectStatus(project) {
    try { return project.status(); } catch(e) { return "active"; }
}

function countRemainingTasks(project) {
    return project.flattenedTasks().filter(function(t) {
        return !t.completed() && !t.dropped();
    }).length;
}

function countActiveProjects(projects) {
    var activeCount = 0;
    for (var i = 0; i < projects.length; i++) {
        var status = getProjectStatus(projects[i]);
        if (status === "active" || status === "active status") activeCount++;
    }
    return activeCount;
}

function serializeFolderSummary(folder) {
    var projects = folder.projects();
    return {
        type: "folder",
        id: folder.id(),
        name: folder.name(),
        projectCount: projects.length,
        activeCount: countActiveProjects(projects)
    };
}

function serializeProjectSummary(project) {
    return {
        type: "project",
        id: project.id(),
        name: project.name(),
        status: getProjectStatus(project),
        taskCount: countRemainingTasks(project)
    };
}
"""

# Reusable JXA: serialize a folder's subfolders and projects into a list.
JS_SERIALIZE_FOLDER_CONTENTS = (
    JS_PROJECT_LIST_HELPERS
    + """\
function serializeFolderContents(folder) {
    var children = [];
    var subfolders = folder.folders();
    for (var i = 0; i < subfolders.length; i++) {
        children.push(serializeFolderSummary(subfolders[i]));
    }
    var projects = folder.projects();
    for (var i = 0; i < projects.length; i++) {
        children.push(serializeProjectSummary(projects[i]));
    }
    return children;
}
"""
)

# ── Complete JS scripts ─────────────────────────────────────────────────

JS_INBOX = (
    """\
"""
    + JS_LOCAL_DATE_HELPERS
    + """\
var doc = Application("OmniFocus").defaultDocument;
var tasks = doc.inboxTasks().filter(function(t) {
    return !t.completed() && !t.dropped();
}).map(function(t) {
    var tags = t.tags().map(function(tg) { return tg.name(); });
    return {
        id: t.id(),
        name: t.name(),
        flagged: t.flagged(),
        completed: t.completed(),
        dueDate: toLocalDateString(t.dueDate()),
        note: t.note(),
        tags: tags
    };
});
JSON.stringify(tasks);
"""
)

JS_TASKS = (
    """\
"""
    + JS_LOCAL_DATE_HELPERS
    + JS_ACTION_TASK_HELPERS
    + """\
var doc = Application("OmniFocus").defaultDocument;
var tasks = doc.flattenedTasks().filter(function(t) {
    return isIndividualAction(t) && !t.completed() && !t.dropped();
}).map(function(t) {
    var tags = t.tags().map(function(tg) { return tg.name(); });
    var proj = t.containingProject();
    return {
        id: t.id(),
        name: t.name(),
        flagged: t.flagged(),
        completed: false,
        dueDate: toLocalDateString(t.dueDate()),
        note: t.note(),
        project: proj ? proj.name() : null,
        tags: tags
    };
});
JSON.stringify(tasks);
"""
)

JS_PROJECTS = """\
var doc = Application("OmniFocus").defaultDocument;
var projects = doc.flattenedProjects().map(function(p) {
    var s;
    try { s = p.status(); } catch(e) { s = "active"; }
    var f = p.folder();
    return {
        id: p.id(),
        name: p.name(),
        status: s,
        taskCount: p.flattenedTasks().length,
        folder: f ? f.name() : null,
        note: p.note()
    };
});
JSON.stringify(projects);
"""

JS_TAGS = """\
var doc = Application("OmniFocus").defaultDocument;
var tags = doc.flattenedTags().map(function(t) {
    return { id: t.id(), name: t.name() };
});
JSON.stringify(tags);
"""

JS_SHOW_PROJECT = (
    """\
"""
    + JS_LOCAL_DATE_HELPERS
    + JS_FUZZY_MATCH
    + """\
var app = Application("OmniFocus");
var doc = app.defaultDocument;

function serializeTask(t) {
    var children = t.tasks();
    return {
        id: t.id(),
        name: t.name(),
        flagged: t.flagged(),
        completed: t.completed(),
        dropped: t.dropped(),
        dueDate: toLocalDateString(t.dueDate()),
        deferDate: toLocalDateString(t.deferDate()),
        note: t.note(),
        tags: t.tags().map(function(tg) { return tg.name(); }),
        sequential: children.length > 0 ? t.sequential() : false,
        children: children.map(serializeTask)
    };
}

var lookup = fuzzyMatch(doc.flattenedProjects(), "__QUERY__");
var result;
if (lookup.error === "not_found") {
    result = {error: "Project not found"};
} else if (lookup.error) {
    result = lookup;
} else {
    var proj = lookup.match;
    var s;
    try { s = proj.status(); } catch(e) { s = "active"; }
    result = {
        id: proj.id(),
        name: proj.name(),
        status: s,
        note: proj.note(),
        sequential: proj.sequential(),
        children: proj.tasks().map(serializeTask)
    };
}
JSON.stringify(result);
"""
)

JS_FOLDERS = """\
var doc = Application("OmniFocus").defaultDocument;
var folders = doc.flattenedFolders().map(function(f) {
    return {
        id: f.id(),
        name: f.name(),
        projectCount: f.projects().length
    };
});
JSON.stringify(folders);
"""

JS_TOP_LEVEL = (
    JS_PROJECT_LIST_HELPERS
    + """\
var doc = Application("OmniFocus").defaultDocument;
var result = [];

// Top-level folders
var folders = doc.folders();
for (var i = 0; i < folders.length; i++) {
    result.push(serializeFolderSummary(folders[i]));
}

// Top-level projects (not in any folder)
var topProjects = doc.projects();
for (var i = 0; i < topProjects.length; i++) {
    result.push(serializeProjectSummary(topProjects[i]));
}

JSON.stringify(result);
"""
)

# ── JXA bridge ──────────────────────────────────────────────────────────

JXA_TIMEOUT_SECONDS = 30
JXA_APP_PREAMBLE = """\
var __ofocusApp = Application("OmniFocus");
__ofocusApp.activate();
delay(0.2);
"""


def run_jxa(script: str) -> Any | None:
    """Run a JXA (not OmniAutomation) script and parse JSON result."""
    full_script = JXA_APP_PREAMBLE + script
    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", full_script],
            capture_output=True,
            text=True,
            check=True,
            timeout=JXA_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        raise OmniError(
            f"JXA error: command timed out after {JXA_TIMEOUT_SECONDS} seconds"
        ) from e
    except subprocess.CalledProcessError as e:
        raise OmniError(f"JXA error: {e.stderr.strip() or e.stdout.strip()}") from e

    stdout = result.stdout.strip()
    if not stdout:
        raise OmniError("JXA error: empty output from osascript")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        raise OmniError(f"Failed to parse JXA output: {stdout!r}")
