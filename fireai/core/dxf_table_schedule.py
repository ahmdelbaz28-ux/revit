"""fireai/core/dxf_table_schedule.py
=================================
Uses proper Autodesk CAD Data objects replacing plain MTEXT lines.
Required functionality for enabling digital data link queries externally
within contractors workflow applications like Navisworks.

Architecture:
  - Uses ezdxf Table addon for native DXF TABLE entity generation
  - Falls back gracefully if ezdxf version does not support Table
  - Device data accepts both dict and object inputs
  - Column widths follow AEC industry plot conventions

Safety:
  - DXF TABLE entities are queryable in Navisworks, AutoCAD Data Extraction,
    and BIM coordination tools. Plain MTEXT is NOT queryable.
  - Using text blocks instead of TABLE entities means the schedule data
    is invisible to digital workflows, leading to manual transcription errors.
"""

from __future__ import annotations

try:
    from ezdxf.addons import TablePainter as Table
except ImportError:
    try:
        from ezdxf.addons import (  # type: ignore[attr-defined, no-redef]
            Table,  # type: ignore[attr-defined,no-redef,import-untyped] # Older ezdxf versions
        )
    except ImportError:
        Table = None  # type: ignore[misc]


class TrueAECDraftingTable:
    """Generates proper DXF TABLE entities for fire alarm device schedules.

    Previous implementations used add_text() for each cell, which does not
    create queryable DXF TABLE entities. This class creates real TABLE
    entities using ezdxf's Table addon, enabling digital data extraction
    in Navisworks, AutoCAD Data Extraction, and BIM coordination tools.

    If the installed ezdxf version does not support the Table addon,
    the draft_device_boq_table() method returns False, and callers
    should fall back to text blocks.

    Parameters
    ----------
        table_position_xyz: (x, y, z) insertion point for the table.

    """

    def __init__(self, table_position_xyz: tuple = (0.0, 0.0, 0.0)):
        self.position = table_position_xyz

    def draft_device_boq_table(self, msp, device_array: list, project_metadata: str = "Fire Alarm Device Log") -> bool:
        """Create a DXF TABLE entity with device schedule data.

        The table includes columns: INDEX_ID, DEVICE_TYPE, CIRCUIT_GROUP,
        ZONE, LOCATION. Each device in the device_array is rendered as a
        data row with its properties.

        Parameters
        ----------
            msp: ezdxf Modelspace object to draw into.
            device_array: List of devices (dicts or objects) with fields:
                - device_id / device_type / circuit_id / zone_id / x / y
            project_metadata: Title text for the table header row.

        Returns
        -------
            True if table was successfully created, False if ezdfx Table
            addon is not available or rendering fails.

        """
        if Table is None:
            # If ezdxf isn't fresh enough
            return False

        headers = ["INDEX_ID", "DEVICE_TYPE", "CIRCUIT_GROUP", "ZONE", "LOCATION"]
        columns_count = len(headers)
        rows_count = len(device_array) + 2  # Including title row + header row

        tbl = Table(insert=self.position, nrows=rows_count, ncols=columns_count)

        # Style settings enforcing AEC plot conventions
        tbl.set_col_width(0, 3.5)
        tbl.set_col_width(1, 5.0)
        tbl.set_col_width(2, 2.5)
        tbl.set_col_width(3, 2.0)
        tbl.set_col_width(4, 5.5)

        # V15 FIX: TablePainter.text_cell() uses 'style' parameter instead of 'bg_color'.
        # The old ezdxf Table addon used bg_color keyword, but TablePainter uses
        # named styles. We use the default style for all cells — background
        # colors can be set via custom styles if needed.
        tbl.text_cell(0, 0, project_metadata)
        # Typically spans logic here using spans, however, let's inject natively mapped string to col 0 simply for AEC compatibility test.

        for i, hname in enumerate(headers):
            tbl.text_cell(1, i, hname)

        r_cursor = 2
        for entity in device_array:
            if isinstance(entity, dict):
                d_id = entity.get("device_id", "Unk")
                d_type = entity.get("device_type", "Undefined")
                c_gr = entity.get("circuit_id", "SLC-01")
                zn = entity.get("zone_id", "ZnX")
                pos = f"({round(entity.get('x', 0), 1)}, {round(entity.get('y', 0), 1)})"
            else:
                d_id = getattr(entity, "device_id", "Unk")
                d_type = getattr(entity, "device_type", "Undefined")
                c_gr = getattr(entity, "circuit_id", "SLC-01")
                zn = getattr(entity, "zone_id", "ZnX")
                try:
                    pos = f"({round(entity.x, 1)}, {round(entity.y, 1)})"
                except Exception:
                    pos = "(0,0)"

            tbl.text_cell(r_cursor, 0, str(d_id))
            tbl.text_cell(r_cursor, 1, str(d_type))
            tbl.text_cell(r_cursor, 2, str(c_gr))
            tbl.text_cell(r_cursor, 3, str(zn))
            tbl.text_cell(r_cursor, 4, str(pos))
            r_cursor += 1

        try:
            tbl.render(msp)
            return True
        except Exception as gen_err:
            print(f"Critical CAD table generation abort: {gen_err}")
            return False
