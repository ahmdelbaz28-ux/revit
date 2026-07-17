#!/usr/bin/env python3
"""
scripts/pack_aps_bundle.py — Automates compiling C# plugins and zipping them
into Autodesk AppBundle ZIP packages for APS Design Automation.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist" / "appbundles"


def compile_project(csproj_path: Path) -> bool:
    """Runs dotnet build in Release mode."""
    print(f"[BUILD] Compiling project: {csproj_path.name} in Release mode...")
    try:
        res = subprocess.run(
            ["dotnet", "build", str(csproj_path), "-c", "Release"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        print(f"[SUCCESS] Compilation succeeded for {csproj_path.name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Compilation failed for {csproj_path.name}:")
        print(e.stderr or e.stdout)
        return False


def zip_directory(src_dir: Path, zip_path: Path):
    """Zips a directory recursively, preserving relative bundle structure."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(src_dir):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(src_dir.parent)
                zipf.write(file_path, arcname)
    print(f"[ZIP] Created bundle archive: {zip_path}")


def pack_autocad_bundle() -> bool:
    """Prepares and packages the AutoCAD AppBundle ZIP."""
    print("\n--- AutoCAD AppBundle Packaging ---")
    csproj = REPO_ROOT / "autocad_addin" / "BazSparkAutoCADBridge" / "BazSparkAutoCADBridge.csproj"
    if not compile_project(csproj):
        return False

    bundle_dir = REPO_ROOT / "autocad_addin" / "BazSparkAutoCADBridge.bundle"
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)

    # Create AutoCAD bundle layout
    contents_dir = bundle_dir / "Contents"
    contents_dir.mkdir(parents=True)

    # Copy PackageContents.xml
    manifest_src = REPO_ROOT / "autocad_addin" / "PackageContents.xml"
    if not manifest_src.exists():
        print(f"[ERROR] Manifest missing: {manifest_src}")
        return False
    shutil.copy2(manifest_src, bundle_dir / "PackageContents.xml")

    # Copy compiled Release DLLs
    bin_dir = REPO_ROOT / "autocad_addin" / "BazSparkAutoCADBridge" / "bin" / "Release"
    if not bin_dir.exists():
        # Try without config-specific subdir if output path is overridden
        bin_dir = REPO_ROOT / "autocad_addin" / "BazSparkAutoCADBridge" / "bin"
    
    target_dlls = ["BazSparkAutoCADBridge.dll", "Newtonsoft.Json.dll", "Speckle.Core.dll", "Speckle.Objects.dll", "Microsoft.Web.WebView2.Wpf.dll", "Microsoft.Web.WebView2.Core.dll"]
    for dll in target_dlls:
        src_dll = bin_dir / dll
        if src_dll.exists():
            shutil.copy2(src_dll, contents_dir / dll)
            print(f"[COPY] Copied DLL: {dll}")

    # Zip the bundle
    zip_path = DIST_DIR / "BazSparkAutoCADBridge.zip"
    zip_directory(bundle_dir, zip_path)

    # Clean up temp bundle directory
    shutil.rmtree(bundle_dir)
    return True


def pack_revit_bundle() -> bool:
    """Prepares and packages the Revit AppBundle ZIP."""
    print("\n--- Revit AppBundle Packaging ---")
    # For Revit, we skip dotnet compilation in this script if Revit SDK is missing (or run it best-effort)
    # We will copy the xml and assemblies if compile was run, or print instruction
    bundle_dir = REPO_ROOT / "revit_addin" / "BazSparkRevitBridge.bundle"
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)

    contents_dir = bundle_dir / "Contents"
    contents_dir.mkdir(parents=True)

    # Copy PackageContents.xml
    manifest_src = REPO_ROOT / "revit_addin" / "PackageContents.xml"
    if not manifest_src.exists():
        print(f"[ERROR] Manifest missing: {manifest_src}")
        return False
    shutil.copy2(manifest_src, bundle_dir / "PackageContents.xml")

    # Copy compiled dlls (best effort check of bin/Release)
    bin_dir = REPO_ROOT / "revit_addin" / "BazSparkRevitBridge" / "bin" / "Release"
    if not bin_dir.exists():
        bin_dir = REPO_ROOT / "revit_addin" / "BazSparkRevitBridge" / "bin"

    # We check if dll exists before copying
    dll = "BazSparkRevitBridge.dll"
    src_dll = bin_dir / dll
    if src_dll.exists():
        shutil.copy2(src_dll, contents_dir / dll)
        print(f"[COPY] Copied DLL: {dll}")
    else:
        print(f"[WARNING] Warning: Compiled DLL '{dll}' not found in {bin_dir}. Run build with Revit SDK installed first.")

    # Zip the bundle
    zip_path = DIST_DIR / "BazSparkRevitBridge.zip"
    zip_directory(bundle_dir, zip_path)

    # Clean up temp bundle directory
    shutil.rmtree(bundle_dir)
    return True


def main():
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    acad_ok = pack_autocad_bundle()
    revit_ok = pack_revit_bundle()

    print("\n========================================")
    if acad_ok and revit_ok:
        print("[SUCCESS] Successfully packed AutoCAD and Revit AppBundles!")
        print(f"Output archives: {DIST_DIR}")
    else:
        print("[WARNING] Completed AppBundle packaging with warnings (check compilation output).")


if __name__ == "__main__":
    main()
