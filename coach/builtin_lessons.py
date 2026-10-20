"""The buttons and panes the coach knows, and the lessons built into the program (used offline)."""


# Buttons the learner must click. Positions are recorded once per screen layout ("Record buttons").
TARGETS = {
    "multiselect": "Multi-Select (Home tab)",
    "select": "Select (Home tab)",
    "length": "Length (Home tab)",
    "area": "Area (Home tab)",
    "perimeter": "Perimeter (Home tab)",
    "count": "Count (Home tab)",
    "trace_area": "Area (Traces panel)",
    "trace_count": "Count (Traces panel)",
    "trace_length": "Length (Traces panel)",
    "trace_perimeter": "Perimeter (Traces panel)",
}
RIBBON = ("multiselect", "select", "length", "area", "perimeter", "count")
# Screen areas the coach reads (recorded the same way as buttons).
PANES = {
    "qtylist": "the Quantity List pane",
}
ALL_TARGETS = {**TARGETS, **PANES}
# Built-in lessons, written to the lessons folder on first run (and replaced when a newer built-in
# version ships). After that the coach reads the lessons folder: the same files the website will serve.
BUILTIN_LESSONS = [
    {
        "id": "getting_around",
        "title": "Getting Around the Window",
        "order": 1,
        "version": 1,
        "guide": "eTakeoff Dimension Online Training Guide",
        "drawing": "004 A1.1 1st Floor Plan",
        "scale": "3/32\" = 1'-0\"",
        "steps": [
            {"id": "ms", "type": "click", "target": "multiselect", "skill": "Navigating the ribbon", "page": 11,
             "text": "On the Home tab, click Multi-Select and notice that your cursor changes."},
            {"id": "sel", "type": "click", "target": "select", "skill": "Navigating the ribbon", "page": 11,
             "text": "Click Select to change it back again."},
        ],
    },
    {
        # Guide p. 28, "Working with Polar mode", practice steps 1-10.
        "id": "taking_measurements",
        "title": "Taking Measurements",
        "order": 2,
        "version": 2,
        "guide": "eTakeoff Dimension Online Training Guide",
        "drawing": "004 A1.1 1st Floor Plan",
        "scale": "3/32\" = 1'-0\"",
        "grading": {"full_credit_within": 0.03, "pass_within": 0.10, "partial_score": 75},
        "steps": [
            {"id": "areabtn", "type": "click", "target": "trace_area", "also": ["area"],
             "skill": "Choosing the right trace", "page": 28,
             "text": "In drawing 004 A1.1 1st Floor Plan, zoom in to grid B5, where you see the Laundry room. "
                     "Then, in the Traces control panel, click Area."},
            {"id": "laundry", "type": "measure", "kind": "area", "expected": 604.42, "points": 8, "dwg": "A1.1",
             "skill": "Polar mode and direction", "page": 28,
             "known": [["bath and elevator included", 1.03, 1.6]],
             "text": "Starting at the top left of the Laundry room, hold down the Ctrl key and click each corner in "
                     "clockwise sequence to define its area, excluding the bathroom and elevator (8 points total). "
                     "Press S when you are finished, then press Enter to submit."},
            {"id": "perbtn", "type": "click", "target": "trace_perimeter", "also": ["perimeter"],
             "skill": "Choosing the right trace", "page": 28,
             "text": "Next, click Perimeter in the Traces control panel."},
            {"id": "elec", "type": "measure", "kind": "perimeter", "expected": 48.86, "points": 4, "dwg": "A1.1",
             "skill": "Choosing the right trace", "page": 28,
             "text": "Directly to the left of the Laundry room, click to measure the perimeter of the Electrical "
                     "room (4 points total). Press S when you are finished, then press Enter to submit."},
            {"id": "desc_laundry", "type": "describe", "of": "laundry", "answer": "Laundry Room Area",
             "skill": "Finish, undo, describe", "page": 28,
             "text": "Return to the area trace over the Laundry room. Click to select it, and then press D. "
                     "Enter  Laundry Room Area  and press Enter. Notice the description now appears in the "
                     "Quantity List and Measurement Summary panes."},
            {"id": "desc_elec", "type": "describe", "of": "elec", "answer": "Electrical Room",
             "skill": "Finish, undo, describe", "page": 28,
             "text": "Assign the description  Electrical Room  to the perimeter trace you completed: click it, "
                     "press D, type the description and press Enter."},
        ],
    },
]
BUILTIN_LESSON = BUILTIN_LESSONS[1]
