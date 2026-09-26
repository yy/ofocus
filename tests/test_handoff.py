"""Exercise the actual generated JXA protocol with a deterministic JS task model."""

import json
import shutil
import subprocess

import click
import pytest

from ofocus.commands.task import build_handoff_script

TOKEN = "D5417AC8-2BA9-4654-9277-13F33E697B99"
PAYLOAD = {
    "id": "testTask001",
    "name": "Wikify this",
    "note": "A source",
    "token": TOKEN,
}


def execute(payload=PAYLOAD, **changes):
    state = dict(
        id=PAYLOAD["id"],
        name=PAYLOAD["name"],
        note=PAYLOAD["note"],
        completed=False,
        dropped=False,
        inbox=True,
        tags=["agent"],
        children=[],
        completions=0,
    )
    state.update(changes)
    harness = r"""
const vm = require('vm');
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const state = input.state;
const task = {name:()=>state.name, completed:()=>state.completed,
              dropped:()=>state.dropped,
              tasks:()=>state.children, tags:{name:()=>state.tags}};
Object.defineProperty(task,'note',{get:()=>()=>state.note,set:value=>{
  state.note=value; if(state.editDuringWrite)state.name='Changed';
}});
const app = {defaultDocument:{flattenedTasks:{whose:q=>()=>q.id===state.id?[task]:[]},
                              inboxTasks:{whose:q=>()=>state.inbox&&q.id===state.id?[task]:[]}},
             markComplete:t=>{state.completed=true;state.completions++;}};
const result = JSON.parse(vm.runInNewContext(input.script, {Application:()=>app}));
process.stdout.write(JSON.stringify({result,state}));
"""
    node = shutil.which("node")
    assert node, "Node is required to test the generated JXA protocol"
    response = subprocess.run(
        [node, "-e", harness],
        input=json.dumps({"state": state, "script": build_handoff_script(payload)}),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(response.stdout)


def test_handoff_and_repeated_ack_preserve_capture():
    first = execute()
    assert first["result"]["status"] == "accepted"
    assert first["state"]["completed"]
    assert first["state"]["note"].startswith(PAYLOAD["note"] + "\n\n[Finch handoff ")
    assert "finch://job/" + TOKEN in first["state"]["note"]
    second = execute(**first["state"])
    assert second["result"] == first["result"]
    assert second["state"] == first["state"]


@pytest.mark.parametrize(
    "changes",
    [
        dict(name="Edited"),
        dict(note="Edited"),
        dict(tags=["Agent"]),
        dict(inbox=False),
        dict(completed=True),
        dict(dropped=True),
        dict(children=[1]),
        dict(id="differentID"),
    ],
)
def test_changed_scope_is_not_completed(changes):
    reply = execute(**changes)
    assert reply["result"]["status"] == "conflict"
    assert reply["state"]["completions"] == 0
    assert reply["state"]["note"] == changes.get("note", PAYLOAD["note"])


def test_capture_is_data_not_javascript():
    text = '"; throw new Error("injected"); // $(touch /tmp/never) `x`\n\\日本語'
    payload = dict(PAYLOAD, name=text, note=text)
    reply = execute(payload, name=text, note=text)
    assert reply["result"]["status"] == "accepted"
    assert reply["state"]["note"].startswith(text)


def test_edit_during_annotation_prevents_completion():
    reply = execute(editDuringWrite=True)
    assert reply["result"]["status"] == "conflict"
    assert reply["state"]["completions"] == 0


@pytest.mark.parametrize(
    "payload", [{}, dict(PAYLOAD, token="bad"), dict(PAYLOAD, note=None)]
)
def test_bad_payload_is_rejected(payload):
    with pytest.raises(click.BadParameter):
        build_handoff_script(payload)
