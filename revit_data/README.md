# Revit API Data

This directory contains pre-generated Revit API data from [RevitAPIDocGen](https://github.com/chuongmep/RevitAPIDocGen).

## Files

- `RevitAPI2022.json` - Revit API data for version 2022
- `RevitAPI2023.json` - Revit API data for version 2023

## Data Format

Each entry contains:
```json
{
    "Title": "DoorCost",
    "Keywords": "ParameterTypeId.DoorCost property",
    "APIName": "P:Autodesk.Revit.DB.ParameterTypeId.DoorCost",
    "Description": "\"Cost\"",
    "Namespace": "Autodesk.Revit.DB",
    "Guid": "efdf5191-47a5-2d99-db4f-b425edebbee6",
    "Type": "property"
}
```

## Usage

Load the data in your application:

```python
from backend.services.revit_integration import get_revit_integration

revit = get_revit_integration()
revit.load_revit_api_data("revit_data/RevitAPI2023.json")

# Search for API entries
results = revit.search_api_data(keyword="Wall.Create")

# Get URL to documentation
url = revit.get_api_url(results[0], "2023")
# Returns: https://www.revitapidocs.com/2023/efdf5191-47a5-2d99-db4f-b425edebbee6.htm
```

## Source

This data was generated using the RevitAPIDocGen project which:
1. Extracts HTML files from Revit API CHM documentation
2. Parses metadata from each HTML file
3. Generates JSON/CSV files with API information

For more information, visit: https://github.com/chuongmep/RevitAPIDocGen
