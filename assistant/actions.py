"""Small, closed tool schemas. No arbitrary callable, command, or raw URI dispatch."""
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import Field, TypeAdapter

from .contracts import Record


class ActionBase(Record):
    """Common binding for a single action; identity is supplied by the host."""
    tool_call_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    generation: int = Field(ge=1)


class OpenURL(ActionBase):
    tool: Literal["system.open_url"] = "system.open_url"
    url: str = Field(min_length=1, max_length=2048)


class LaunchApp(ActionBase):
    tool: Literal["system.launch_app"] = "system.launch_app"
    app_id: str = Field(min_length=1, max_length=80)


class CreateFile(ActionBase):
    tool: Literal["file.create_new"] = "file.create_new"
    path: str = Field(min_length=1, max_length=1024)
    content: str = Field(max_length=4000)


class Click(ActionBase):
    tool: Literal["desktop.click"] = "desktop.click"
    control_id: str = Field(min_length=1, max_length=256)


class FocusWindow(ActionBase):
    """Focus one host-observed window; never search by a model-provided fuzzy title."""
    tool: Literal["desktop.focus_window"] = "desktop.focus_window"
    hwnd: int = Field(gt=0)


class FocusControl(ActionBase):
    """Focus a host-identified editable control without submitting or clicking arbitrary UI."""
    tool: Literal["desktop.focus_control"] = "desktop.focus_control"
    control_id: str = Field(min_length=1, max_length=256)


class TypeText(ActionBase):
    tool: Literal["desktop.type_text"] = "desktop.type_text"
    control_id: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=80)


class Scroll(ActionBase):
    tool: Literal["desktop.scroll"] = "desktop.scroll"
    direction: Literal["up", "down"]
    ticks: int = Field(ge=1, le=3)


class Shortcut(ActionBase):
    tool: Literal["desktop.shortcut"] = "desktop.shortcut"
    keys: str = Field(min_length=1, max_length=40)


class FixtureAction(ActionBase):
    """In-memory counter for explicit test mode. Cannot operate desktop or files."""
    tool: Literal["fixture.increment"] = "fixture.increment"
    amount: int = Field(default=1, ge=1, le=3)


Action = Annotated[OpenURL | LaunchApp | CreateFile | Click | FocusWindow | FocusControl | TypeText | Scroll | Shortcut | FixtureAction,
                   Field(discriminator="tool")]
ACTION_SCHEMA = TypeAdapter(Action)
