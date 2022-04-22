import appdaemon.plugins.hass.hassapi as hass

VALID_COMMANDS = frozenset(["/vacuumHome", "/vacuumLocate", "/vacuum"])


class VacuumState(object):
    none = 0
    waiting_start = 1
    waiting_dock = 2


class RobotVacuumManager(hass.Hass):
    def initialize(self):
        # list of chats to notify
        self.telegram_list = self.args.get("telegram") or []
        # entity id
        self.entity = self.args.get("entity")
        self.bin_entity = self.args.get("bin_entity")

        # the time to begin auto vacuum
        self.schedule_time = self.args.get("schedule_time")

        self.run_daily(self.on_schedule, self.schedule_time)
        self.listen_event(self.receive_telegram_command, "telegram_command")
        self.listen_state(self.receive_state_change, self.entity)
        if self.bin_entity:
            self.listen_state(self.receive_state_change, self.bin_entity)

        self._vacuum_state = VacuumState.none

        self._activation_handle = None
        self._timeout_handle = None

    def _timeout_state_change(self, kwargs):
        if self._vacuum_state == VacuumState.none:
            return

        if self._vacuum_state == VacuumState.waiting_start:
            self.log("timed out on waiting_start")
            self._send_message("WARNING: Timed out waiting for vacuum to start")

        elif self._vacuum_state == VacuumState.waiting_dock:
            self.log("timed out on waiting_arm")
            self._send_message(
                "WARNING: Timed out waiting for vacuum to return to dock"
            )

        else:
            raise NotImplementedError

        self._vacuum_state = VacuumState.none
        self._cancel_timers()

    def _cancel_timers(self):
        if self._timeout_handle:
            self.cancel_timer(self._timeout_handle)
            self._timeout_handle = None

        if self._activation_handle:
            self.cancel_timer(self._activation_handle)
            self._activation_handle = None

    def _send_message(self, message, target_list=None):
        if target_list is None:
            target_list = self.telegram_list
        for target in target_list:
            self.call_service(
                "telegram_bot/send_message",
                target=target,
                message=f"*Robovac:* {message}",
            )

    def on_schedule(self, kwargs):
        self._cancel_timers()
        self._timeout_handle = self.run_in(self._timeout_state_change, 60)
        self._vacuum_state = VacuumState.waiting_start
        # if robot isnt dock, we got a problem
        state = self.get_state(self.entity)
        if state == "docked":
            self.call_service(
                "vacuum/start",
                entity_id=self.entity,
            )
        else:
            self.log(
                f"Vacuum could not be scheduled because state is '{state}' instead of 'docked'"
            )

    def receive_state_change(self, entity, attribute, old, new, kwargs):
        self.log(f"recived new state for {entity}: {new}")
        if entity == self.bin_entity:
            if old == "off" and new == "on":
                self._send_message("You need to empty the bin")
        if entity == self.entity:
            if self._vacuum_state == "error":
                self._send_message("I had an accident, please check on me")
            elif self._vacuum_state == VacuumState.waiting_dock:
                if new == "docked":
                    self._send_message("Returned to dock")
                    self._vacuum_state = VacuumState.none
                    if self._timeout_handle:
                        self.cancel_timer(self._timeout_handle)
                        self._timeout_handle = None
                elif new == "returning_to_dock":
                    pass
                else:
                    self.log(
                        f"received unexpected vacuum state change to {new} while waiting_dock"
                    )

            elif self._vacuum_state == VacuumState.waiting_start:
                if new == "cleaning":
                    self._send_message("Sweepin' the floors")
                    self._vacuum_state = VacuumState.none
                    if self._timeout_handle:
                        self.cancel_timer(self._timeout_handle)
                        self._timeout_handle = None
                else:
                    self.log(
                        f"received unexpected vacuum state change to {new} while waiting_start"
                    )

    def receive_telegram_command(self, event_id, payload_event, *args):
        assert event_id == "telegram_command"

        command = payload_event["command"]

        if command not in VALID_COMMANDS:
            return

        self.log(f"received {command} command")

        chat_id = payload_event["chat_id"]

        # all valid commands will cancel automatic starting
        if self._activation_handle:
            self.cancel_timer(self._activation_handle)
            self._activation_handle = None

        if command == "/vacuum":
            if self.get_state(self.entity) != "cleaning":
                if self._timeout_handle:
                    self.cancel_timer(self._timeout_handle)
                self._timeout_handle = self.run_in(self._timeout_state_change, 60)
                self._vacuum_state = VacuumState.waiting_start
                self.call_service(
                    "vacuum/start",
                    entity_id=self.entity,
                )

        elif command == "/vacuumDock":
            if self.get_state(self.entity) != "docked":
                self._cancel_timers()
                self._timeout_handle = self.run_in(self._timeout_state_change, 60)
                self._vacuum_state = VacuumState.waiting_dock
                self.call_service(
                    "vacuum/return_to_base",
                    entity_id=self.entity,
                )
            else:
                self._send_message(
                    message="Vacuum is already docked",
                    target_list=[chat_id],
                )

        elif command == "/vacuumLocate":
            self.call_service(
                "vacuum/locate",
                entity_id=self.entity,
            )

    def terminate(self):
        self._cancel_timers()
