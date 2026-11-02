"""Reuse actual upstream animation categories and a transient presentation mask."""
from PySide6.QtWidgets import QWidget


class PetPresentation:
    def __init__(self, shell):
        self.shell = shell
        self.suppressed = []
        self.legacy = []
        self.working = False

    def targets(self):
        if self.shell is None:
            return []
        from pet.multi_window_shared import presentation_targets
        return presentation_targets(self.shell)

    def animate(self, state, *, verified=False, live=True):
        desired = {"INTERPRETING": ["原地专心玩魔方"], "EXECUTING": ["原地专心玩魔方"], "VERIFYING": ["原地专心玩魔方"], "TRANSCRIBING": ["原地专心玩魔方"], "CAPTURING": ["东张西望"],
                   "WAITING_APPROVAL": ["东张西望"], "WAITING_CLARIFICATION": ["东张西望"],
                   "SUCCEEDED": ["点击回应-开心跃动"] if verified and live else []}.get(state, [])
        for target in self.targets():
            categories = getattr(target, "cats", {})
            names = [name for group in categories.values() for name in group]
            chosen = next((actual for candidate in desired for actual in names if actual.replace(" - ", "-") == candidate), None)
            if chosen and live:
                target.request_link_anim(chosen)
            elif callable(getattr(target, "request_link_idle", None)):
                target.request_link_idle()

    def set_working(self, working):
        if working == self.working:
            return
        self.working = working
        if working:
            for target in self.targets():
                hide_bubble = getattr(target, "hide_bubble", None)
                if callable(hide_bubble):
                    hide_bubble()
                all_sprites = getattr(target, "_all_sprites", None)
                if callable(all_sprites):
                    for sprite in all_sprites():
                        sprite.set_assistant_suppressed(True)
                        self.suppressed.append(sprite)
                elif isinstance(target, QWidget):
                    self.legacy.append((target, target.windowOpacity(), getattr(target, "mouse_through", False)))
                    target.setWindowOpacity(0)
                    target.mouse_through = True
        else:
            for sprite in self.suppressed:
                sprite.set_assistant_suppressed(False)
            self.suppressed.clear()
            for target, opacity, through in self.legacy:
                cfg = getattr(target, "cfg", None)
                target.setWindowOpacity(float(cfg.get("pet_opacity", opacity*100))/100 if cfg else opacity)
                target.mouse_through = bool(cfg.get("mouse_through", through)) if cfg else through
            self.legacy.clear()

    def close(self):
        self.set_working(False)
