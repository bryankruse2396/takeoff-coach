r"""
Takeoff Coach (the version number is COACH_VERSION in coach/config.py)
================================
Coaches a learner through eTakeoff Dimension steps on top of the real program:
  * shows the instruction as a callout over eTakeoff, with an arrow to the button (Practice mode)
  * tracks clicks and counts wrong ones
  * reads each finished measurement off eTakeoff's Quantity List (instant) and grades the real quantity,
    then double-checks it against eTakeoff's own data (point count, drawing) once eTakeoff publishes it
  * scores every step and saves a results report
  * signs in to the training site, downloads lessons and tests, and uploads every session automatically
  * Tests: the site draws random blocks in a random order; a test can't be paused or resumed, and it
    ends after a set time with no activity

Learners use the packaged program, TakeoffCoach.exe (download it from the training site; it updates
itself). To run it from source instead:
Setup (once):
    pip install comtypes pynput          (already installed if you ran the probes)
    pip install mss pillow winrt-runtime winrt-Windows.Foundation winrt-Windows.Foundation.Collections winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging winrt-Windows.Storage.Streams winrt-Windows.Globalization
Run (PowerShell), with eTakeoff open on the project you will practice in:
    cd $env:USERPROFILE\Downloads
    python takeoff_coach.py
The coach finds eTakeoff's buttons and Quantity List by reading the screen when a lesson starts.
If it can't, "Record manually" lets you point them out (hover + F8).

Privacy: while a lesson runs it records mouse clicks inside the eTakeoff window
and reads measurement quantities. During a lesson it reacts only to S and Enter pressed in
eTakeoff (the "finish measurement" keys) and nothing typed is recorded; during "Record" it
reacts only to F8. Results are saved to Documents\TakeoffCoach and sent to your account on the
training site: the lesson or test, time spent, each step's result and score. Nothing you type is sent.
"""
