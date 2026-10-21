"""The buttons and panes the coach knows, and the lessons built into the program (used offline)."""


# Buttons the learner must click. Positions are recorded once per screen layout ("Record buttons").
TARGETS = {
    "multiselect": "Multi-Select (Home tab)",
    "select": "Select (Home tab)",
    "length": "Length (Home tab)",
    "area": "Area (Home tab)",
    "perimeter": "Perimeter (Home tab)",
    "count": "Count (Home tab)",
    "disconnected": "Disconnected Point (Home tab)",
    "trace_area": "Area (Traces panel)",
    "trace_count": "Count (Traces panel)",
    "trace_length": "Length (Traces panel)",
    "trace_perimeter": "Perimeter (Traces panel)",
}
RIBBON = ("multiselect", "select", "length", "area", "perimeter", "count", "disconnected")
# Screen areas the coach reads (recorded the same way as buttons).
PANES = {
    "qtylist": "the Quantity List pane",
}
ALL_TARGETS = {**TARGETS, **PANES}
# Built-in lessons (Takeoff Training's own wording), written to the lessons folder on first run (and replaced when a newer built-in
# version ships). After that the coach reads the lessons folder: the same files the website will serve.
BUILTIN_LESSONS = [{'id': 'getting_around',
  'title': 'Navigate the window',
  'order': 1,
  'version': 2,
  'drawing': '004 A1.1 1st Floor Plan',
  'scale': '3/32" = 1\'-0"',
  'steps': [{'id': 'ms',
             'type': 'click',
             'target': 'multiselect',
             'skill': 'Navigating the ribbon',
             'text': 'Find Multi-Select on the Home tab and click it. Watch the pointer: it changes to show that box '
                     'selection is on.'},
            {'id': 'sel',
             'type': 'click',
             'target': 'select',
             'skill': 'Navigating the ribbon',
             'text': 'Now click Select on the Home tab to get the normal pointer back.'}]},
 {'id': 'taking_measurements',
  'title': 'Measure an area and a perimeter',
  'order': 2,
  'version': 3,
  'drawing': '004 A1.1 1st Floor Plan',
  'scale': '3/32" = 1\'-0"',
  'grading': {'full_credit_within': 0.03, 'pass_within': 0.1, 'partial_score': 75},
  'steps': [{'id': 'areabtn',
             'type': 'click',
             'target': 'trace_area',
             'also': ['area'],
             'skill': 'Choosing the right trace',
             'text': 'Open 004 A1.1 1st Floor Plan and zoom to the Laundry room near grid B5. Then pick the Area trace '
                     'in the Traces control panel.'},
            {'id': 'laundry',
             'type': 'measure',
             'kind': 'area',
             'expected': 604.42,
             'points': 8,
             'dwg': 'A1.1',
             'skill': 'Polar mode and direction',
             'known': [['bath and elevator included', 1.03, 1.6]],
             'text': "Trace the Laundry room floor, leaving the bathroom and the elevator out. Begin at the room's "
                     'top-left corner and go clockwise, holding Ctrl so every wall stays straight: one click per '
                     'corner, 8 in all. Press S to close the shape, then Enter to submit.'},
            {'id': 'perbtn',
             'type': 'click',
             'target': 'trace_perimeter',
             'also': ['perimeter'],
             'skill': 'Choosing the right trace',
             'text': 'Pick the Perimeter trace in the Traces control panel.'},
            {'id': 'elec',
             'type': 'measure',
             'kind': 'perimeter',
             'expected': 48.86,
             'points': 4,
             'dwg': 'A1.1',
             'skill': 'Choosing the right trace',
             'text': 'The Electrical room is the small room just left of the Laundry room. Click its 4 corners to run '
                     'around its walls, press S, then Enter to submit.'},
            {'id': 'desc_laundry',
             'type': 'describe',
             'of': 'laundry',
             'answer': 'Laundry Floor Area',
             'skill': 'Finish, undo, describe',
             'text': 'Select your Laundry room area, press D, type  Laundry Floor Area  and press Enter.'},
            {'id': 'desc_elec',
             'type': 'describe',
             'of': 'elec',
             'answer': 'Electrical Room Walls',
             'skill': 'Finish, undo, describe',
             'text': 'Select the Electrical room perimeter, press D, type  Electrical Room Walls  and press Enter.'}]}]
BUILTIN_LESSON = BUILTIN_LESSONS[1]
