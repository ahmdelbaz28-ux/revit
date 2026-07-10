"""
Creates a Drafting View

TESTED REVIT API: -

Author: Gui Talarico | github.com/gtalarico

This file is shared on www.revitapidocs.com
For more information visit http://github.com/gtalarico/revitapidocs
License: http://github.com/gtalarico/revitapidocs/blob/master/LICENSE.md
"""

#  Drafting Views
from Autodesk.Revit.DB import (
    FilteredElementCollector,
    Transaction,
    ViewDrafting,
    ViewFamily,
    ViewFamilyType,
)

uidoc = __revit__.ActiveUIDocument
doc = __revit__.ActiveUIDocument.Document

t = Transaction(doc, 'Create Drafting View')
t.Start()

"""Create a Drafting View"""
def get_drafting_type_id():
    """Selects First available ViewType that Matches Drafting Type."""
    viewfamily_types = FilteredElementCollector(doc).OfClass(ViewFamilyType)
    for i in viewfamily_types:
        if i.ViewFamily == ViewFamily.Drafting:
            return i.Id
    return None

drafting_type_id = get_drafting_type_id()
drafting_view = ViewDrafting.Create(doc, drafting_type_id)
# drafting_view.Name = 'New View' - Optional View Name - May fail if already exists.

t.Commit()
