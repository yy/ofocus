"""JXA bridge and JavaScript snippet constants."""

from typing import Any

from ofocus.bridge import run_osascript_json

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
    var project = t.containingProject();
    return project && t.tasks().length === 0;
}
"""

# Reusable JXA function: fuzzy-match an item from a collection by ID or name.
# `collection` is a JXA specifier (not pre-resolved array) — e.g.
# doc.flattenedProjects, NOT doc.flattenedProjects().
# Uses .whose() for instant server-side exact-ID lookup before falling back
# to linear scan for prefix/name matching.
# Returns {match: item} on unique match, {error: "ambiguous", matches: [...]}
# on multiple, or {error: "not_found"} on none.
JS_FUZZY_MATCH = """\
function fuzzyMatch(collection, query) {
    var i;
    // Exact ID via native .whose() — server-side, near-instant
    try {
        var exact = collection.whose({id: query})();
        if (exact.length === 1) return {match: exact[0]};
    } catch(e) { /* fall through to linear scan */ }
    // Resolve full collection for prefix and name matching
    var items = collection();
    // Exact ID (fallback if .whose() failed)
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
# Uses a tiered strategy to keep common lookups fast without changing
# global prefix semantics:
#   1. .whose({id: query}) — native server-side exact-ID lookup (instant)
#   2. doc.flattenedTasks.id()/name() — global prefix scan over scalar values
#   3. doc.flattenedTasks() — full object scan as a compatibility fallback
# Returns {match: task} on unique match, {error: "ambiguous", matches: [...]}
# on multiple, or {error: "Task not found"} on none.
JS_FIND_TASK_BY_ID = """\
function serializeTaskMatches(ids, names) {
    var matches = [];
    for (var i = 0; i < ids.length; i++) {
        matches.push({id: ids[i], name: names[i]});
    }
    return matches;
}

function findTaskById(doc, query) {
    var i;
    // Tier 1: exact ID via native .whose() — server-side, near-instant
    try {
        var exact = doc.flattenedTasks.whose({id: query})();
        if (exact.length === 1) return {match: exact[0]};
    } catch(e) { /* fall through */ }

    // Tier 2: scan global task IDs/names without materializing task objects
    try {
        var ids = doc.flattenedTasks.id();
        var names = doc.flattenedTasks.name();
        var prefixIds = [];
        var prefixNames = [];
        for (i = 0; i < ids.length; i++) {
            if (ids[i].indexOf(query) === 0) {
                prefixIds.push(ids[i]);
                prefixNames.push(names[i]);
            }
        }
        if (prefixIds.length === 0) return {error: "Task not found"};
        if (prefixIds.length > 1) return {
            error: "ambiguous",
            matches: serializeTaskMatches(prefixIds, prefixNames)
        };
        var unique = doc.flattenedTasks.whose({id: prefixIds[0]})();
        if (unique.length === 1) return {match: unique[0]};
    } catch(e) { /* fall through to full object scan */ }

    // Tier 3: full scan — compatibility fallback if scalar lookup is unsupported
    var all = doc.flattenedTasks();
    var matches = [];
    for (i = 0; i < all.length; i++) {
        if (all[i].id().indexOf(query) === 0) matches.push(all[i]);
    }
    if (matches.length === 0) return {error: "Task not found"};
    if (matches.length > 1) return {
        error: "ambiguous",
        matches: matches.map(function(t) { return {id: t.id(), name: t.name()}; })
    };
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
    + """\
var doc = Application("OmniFocus").defaultDocument;
var ids = doc.flattenedTasks.id();
var names = doc.flattenedTasks.name();
var flagged = doc.flattenedTasks.flagged();
var completed = doc.flattenedTasks.completed();
var dropped = doc.flattenedTasks.dropped();
var dueDates = doc.flattenedTasks.dueDate();
var notes = doc.flattenedTasks.note();
var projectNames = doc.flattenedTasks.containingProject.name();
var projectStatuses = doc.flattenedTasks.containingProject.status();
var childTasks = doc.flattenedTasks.tasks();
var tagNames = doc.flattenedTasks.tags.name();
var tasks = [];
for (var i = 0; i < ids.length; i++) {
    var isActiveProject =
        projectStatuses[i] === "active" || projectStatuses[i] === "active status";
    if (
        !projectNames[i] ||
        !isActiveProject ||
        childTasks[i].length !== 0 ||
        completed[i] ||
        dropped[i]
    ) {
        continue;
    }
    tasks.push({
        id: ids[i],
        name: names[i],
        flagged: flagged[i],
        completed: false,
        dueDate: toLocalDateString(dueDates[i]),
        note: notes[i],
        project: projectNames[i],
        tags: tagNames[i] || []
    });
}
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

var lookup = fuzzyMatch(doc.flattenedProjects, "__QUERY__");
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
    return run_osascript_json(
        full_script,
        timeout_seconds=JXA_TIMEOUT_SECONDS,
        error_prefix="JXA",
    )
