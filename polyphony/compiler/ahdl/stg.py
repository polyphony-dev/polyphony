from .ahdl import *
from logging import getLogger
logger = getLogger(__name__)


class STG(object):
    "State Transition Graph"
    def __init__(self, name, parent, hdlmodule):
        self.name:str = name
        self.parent:STG = parent
        self._states:list[State] = []
        self._state_map:dict[str, State] = {}
        self.hdlmodule = hdlmodule
        self.scheduling = ''

    def __str__(self):
        s = ''
        for state in self._states:
            s += str(state)
        return s

    @property
    def states(self) -> tuple[State]:
        return tuple(self._states)

    def new_state(self, name: str, block: AHDL_BLOCK, step: int) -> State:
        return State(name, block, step, self)

    def has_state(self, state_name: str) -> bool:
        return state_name in self._state_map

    def get_state(self, state_name: str) -> State:
        return self._state_map[state_name]

    def is_main(self):
        return not self.parent

    def set_states(self, states:list[State]):
        self._state_map.clear()
        self._states.clear()
        for s in states:
            self._state_map[s.name] = s
        self._states = states[:]

    def add_states(self, states:list[State]):
        for s in states:
            self._state_map[s.name] = s
        self._states += states[:]

    def remove_state(self, state):
        self._states.remove(state)
        del self._state_map[state.name]
