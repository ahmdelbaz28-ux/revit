"""
BETA SOFTWARE LICENSE AGREEMENT (EULA v2)
======================================

⚠️  WARNING: THIS SOFTWARE IS BETA - NOT FOR PRODUCTION USE

This Fire Protection Analysis Software ("Software") is provided for 
testing and evaluation purposes ONLY.

LIMITATIONS
-----------
1. NOT reviewed by licensed Fire Protection Engineer (FPE)
2. NOT certified by Professional Engineer (PE)
3. NOT approved by Authority Having Jurisdiction (AHJ)
4. Results are PRELIMINARY and require verification

REQUIRED VERIFICATION
---------------------
Before using ANY output from this software:
- Submit to licensed FPE for review
- Obtain PE stamp from fire protection specialist
- Get AHJ approval for final design

LIABILITY DISCLAIMER
--------------------
The user assumes ALL liability for:
- System non-compliance with NFPA 72
- Code violations discovered during inspection
- Legal consequences from improper use
- Injury or death resulting from reliance on unverified outputs

By using this software, you acknowledge:
- This is BETA software under development
- You will NOT use outputs for final design
- You will submit ALL outputs to FPE review before implementation
- You assume full liability for any use without FPE review

NFPA 72 COMPLIANCE
----------------
This software assists with NFPA 72 §17.6 coverage calculations but does NOT
guarantee compliance. Final compliance determination requires:
- Licensed FPE review
- AHJ approval
- On-site inspection

LICENSE GRANT
------------
Permission is granted to use this software for:
- Internal testing and evaluation
- Generating preliminary reports for FPE review
- Educational purposes

Permission is DENIED for:
- Final design decisions
- Construction without FPE/PE approval
- Submittal to AHJ without proper verification

---
Version: 2.0 (2026-05-15)
Status: BETA - NOT FOR PRODUCTION USE
Review Required: YES - Licensed FPE
"""

# This file will be displayed when users run the software
BETA_EULA = """
╔══════════════════════════════════════════════════════════════════╗
║  ⚠️  BETA SOFTWARE — NOT FOR PRODUCTION USE                    ║
║                                                                  ║
║  This software is under development and has NOT been reviewed  ║
║  by a licensed Fire Protection Engineer (FPE).                   ║
║                                                                  ║
║  ALL outputs are PRELIMINARY and MUST be verified by:           ║
║  → Licensed FPE (Fire Protection Engineer)                       ║
║  → PE (Professional Engineer) with fire protection specialty    ║
║  → AHJ (Authority Having Jurisdiction)                            ║
║                                                                  ║
║  Using this software for final design WITHOUT FPE review         ║
║  violates NFPA 72 and may result in:                            ║
║  → System non-compliance                                         ║
║  → Legal liability                                               ║
║  → Injury or death                                               ║
║                                                                  ║
║  By using this software, you acknowledge:                        ║
║  → This is a BETA testing tool                                  ║
║  → You will NOT use outputs for final design                    ║
║  → You will submit ALL outputs to FPE review                    ║
║  → You assume full liability for any use without FPE review      ║
╚══════════════════════════════════════════════════════════════════╝
"""


def print_eula_and_exit():
    """Print EULA and exit if user doesn't accept."""
    print(BETA_EULA)
    response = input("\nDo you accept these terms? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("\n❌ EULA not accepted. Exiting.")
        exit(1)
    print("\n✅ EULA accepted. Proceeding with BETA software...")


if __name__ == "__main__":
    print_eula_and_exit()