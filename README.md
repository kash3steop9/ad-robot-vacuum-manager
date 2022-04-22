# Robot Vacuum Manager for AppDaemon

Some helpful automations and telegram support for Roomba.

```yaml
robot_vacuum_manager:
  module: robot_vacuum_manager
  class: RobotVacuumManager
  dependencies: sentry
  entity: vacuum.roomba
  telegram:
    - !secret telegram_group_id_home
  schedule_time: "12:00:00"
```

Also take a look at the `vacuum-card` project: https://github.com/denysdovhan/vacuum-card
