# Takeoff Coach

On-screen coach for eTakeoff Dimension training. Learners download **TakeoffCoach.exe** from the
training site (it links to the latest release here) and the program updates itself.

- `takeoff_coach.py`: the coach. Bump `COACH_VERSION` to publish a new release.
- `.github/workflows/build.yml`: builds the .exe on Windows, self-tests it, and publishes the release
  with `latest.json`, which the coach's updater reads.
