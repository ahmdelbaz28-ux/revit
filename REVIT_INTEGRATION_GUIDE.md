# Revit Integration Guide

## Overview

This integration provides **complete control over Revit** through multiple connection methods, allowing AI agents to execute commands and manage BIM projects programmatically.

## Features

### Connection Methods

| Method | Description | Requirements | Performance |
|--------|-------------|--------------|--------------|
| **API** | Direct Revit API via pythonnet | Revit installed + pythonnet | Best |
| **Macro** | Revit Macro API (runs inside Revit) | Revit Macro Server | Good |
| **Simulation** | Development mode (no Revit) | None | N/A |

### Element Operations

- **Create**: Walls, Floors, Doors, Windows, Columns, Beams, Family Instances
- **Read**: FilteredElementCollector patterns, Get by ID, Get Selected
- **Update**: Set parameters, Modify properties
- **Delete**: Remove elements

### AI-Powered Commands

Execute natural language commands:
```python
# Example AI commands
revit.execute_ai_command("Create a wall from 0,0,0 to 5000,0,0 on Level 1")
revit.execute_ai_command("Create a door in the selected wall")
revit.execute_ai_command("Get all walls in the project")
revit.execute_ai_command("Delete element with id 12345")
revit.execute_ai_command("Search api for Wall.Create")
```

## Quick Start

### 1. Connect to Revit

```bash
# Using direct API (requires Revit)
curl -X POST "http://localhost:8000/api/v1/revit-integration/connect" \
  -H "Content-Type: application/json" \
  -d '{"method": "api"}'

# Simulation mode (development)
curl -X POST "http://localhost:8000/api/v1/revit-integration/connect" \
  -H "Content-Type: application/json" \
  -d '{"method": "simulation"}'
```

### 2. Create Elements

```bash
# Create a wall
curl -X POST "http://localhost:8000/api/v1/revit-integration/elements/create/wall" \
  -H "Content-Type: application/json" \
  -d '{
    "start_point": [0, 0, 0],
    "end_point": [5000, 0, 0],
    "height": 3000,
    "level": "Level 1"
  }'

# Create a door
curl -X POST "http://localhost:8000/api/v1/revit-integration/elements/create/door" \
  -H "Content-Type: application/json" \
  -d '{
    "host_wall_id": "12345",
    "location_point": [2500, 0, 0],
    "family_type": "M_Single-Flush",
    "level": "Level 1"
  }'
```

### 3. Query Elements

```bash
# Get all walls
curl "http://localhost:8000/api/v1/revit-integration/elements?category=Walls"

# Get selected elements
curl "http://localhost:8000/api/v1/revit-integration/elements/selected"

# Get element by ID
curl "http://localhost:8000/api/v1/revit-integration/elements/12345"
```

### 4. AI Command Execution

```bash
curl -X POST "http://localhost:8000/api/v1/revit-integration/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "Create a door in the selected wall"
  }'
```

## API Endpoints

### Connection
- `POST /api/v1/revit-integration/connect` - Connect to Revit
- `POST /api/v1/revit-integration/disconnect` - Disconnect
- `GET /api/v1/revit-integration/status` - Get status

### Document
- `POST /api/v1/revit-integration/document/open` - Open RVT file
- `POST /api/v1/revit-integration/document/save` - Save document
- `POST /api/v1/revit-integration/document/close` - Close document

### Elements - Create
- `POST /api/v1/revit-integration/elements/create/wall` - Create wall
- `POST /api/v1/revit-integration/elements/create/floor` - Create floor
- `POST /api/v1/revit-integration/elements/create/door` - Create door
- `POST /api/v1/revit-integration/elements/create/window` - Create window
- `POST /api/v1/revit-integration/elements/create/column` - Create column
- `POST /api/v1/revit-integration/elements/create/beam` - Create beam
- `POST /api/v1/revit-integration/elements/create/family` - Create family instance

### Elements - Read
- `GET /api/v1/revit-integration/elements` - Get all elements
- `GET /api/v1/revit-integration/elements/selected` - Get selected
- `GET /api/v1/revit-integration/elements/{id}` - Get by ID
- `GET /api/v1/revit-integration/elements/{id}/parameters` - Get parameters

### Elements - Update/Delete
- `PUT /api/v1/revit-integration/elements/{id}/parameters` - Update parameters
- `DELETE /api/v1/revit-integration/elements/{id}` - Delete element

### Views & Levels
- `GET /api/v1/revit-integration/views` - Get all views
- `POST /api/v1/revit-integration/views` - Create view
- `GET /api/v1/revit-integration/levels` - Get all levels
- `POST /api/v1/revit-integration/levels` - Create level
- `GET /api/v1/revit-integration/grids` - Get all grids
- `GET /api/v1/revit-integration/worksets` - Get all worksets

### Families
- `GET /api/v1/revit-integration/families/{category}/symbols` - Get family symbols
- `POST /api/v1/revit-integration/families/load` - Load family

### Search
- `POST /api/v1/revit-integration/search/api` - Search local API data
- `GET /api/v1/revit-integration/search/online` - Search RevitAPIDocs.com
- `POST /api/v1/revit-integration/data/load` - Load API data file

### AI & Transactions
- `POST /api/v1/revit-integration/execute` - Execute AI command
- `POST /api/v1/revit-integration/transaction/start` - Start transaction
- `POST /api/v1/revit-integration/transaction/commit` - Commit transaction
- `POST /api/v1/revit-integration/transaction/rollback` - Rollback transaction

## Using RevitAPIDocGen Data

The integration includes pre-generated Revit API data for offline use:

```python
# Load API data
revit.load_revit_api_data("revit_data/RevitAPI2023.json")

# Search for API entries
results = revit.search_api_data(keyword="Wall.Create")

# Get documentation URL
url = revit.get_api_url(results[0], "2023")
# Returns: https://www.revitapidocs.com/2023/{guid}.htm
```

## Data Source

This integration incorporates code and patterns from:

1. **gtalarico/revitapidocs.code** - Code samples for Revit API
2. **BIMCoderLiang/RevitJumper** - Query.cs for searching RevitAPIDocs.com
3. **chuongmep/RevitAPIDocGen** - JSON data for Revit API offline access

## Revit API Key Concepts

### FilteredElementCollector

The main pattern for querying elements in Revit:

```python
from Autodesk.Revit.DB import FilteredElementCollector, Wall, BuiltInCategory

# Get all walls
collector = FilteredElementCollector(doc)
collector.OfClass(Wall)
walls = collector.ToElements()

# Using category
collector = FilteredElementCollector(doc)
collector.OfCategory(BuiltInCategory.OST_Walls)
walls = collector.ToElements()
```

### Transaction

All modifications require a transaction:

```python
from Autodesk.Revit.DB import Transaction

t = Transaction(doc, "Create Wall")
t.Start()
# ... make changes ...
t.Commit()
```

### Family Symbol Pattern

Finding and using family types:

```csharp
// From RevitJumper - GetFamilySymbolByName
public static FamilySymbol GetFamilySymbolByName(Document doc, string name)
{
    var paramId = new ElementId(BuiltInParameter.ALL_MODEL_FAMILY_NAME);
    var paramValueProvider = new ParameterValueProvider(paramId);
    var equalsRule = new FilterStringEquals();
    var filterRule = new FilterStringRule(paramValueProvider, equalsRule, name, false);
    var filter = new ElementParameterFilter(filterRule);

    var fec = new FilteredElementCollector(doc);
    fec.OfClass(typeof(FamilySymbol)).WhereElementIsElementType().WherePasses(filter);

    if (fec.GetElementCount() == 1)
    {
        var symbol = fec.FirstElement() as FamilySymbol;
        if (!symbol.IsActive)
        {
            symbol.Activate();
            doc.Regenerate();
        }
        return symbol;
    }
    return null;
}
```

## Troubleshooting

### "Revit API not available"

1. Ensure Revit is installed on Windows
2. Install pythonnet: `pip install pythonnet`
3. Use simulation mode for development

### "Element not found"

1. Verify element ID is correct
2. Check if document is open
3. Ensure element hasn't been deleted

### "Transaction failed"

1. Check if document is editable
2. Verify user has necessary permissions
3. Try rolling back and retrying

## License

This integration uses code and patterns from:
- RevitAPIDocs - MIT License
- RevitJumper - For study, not commercial use
- RevitAPIDocGen - MIT License
