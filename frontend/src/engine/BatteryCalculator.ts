
/**
 * BatteryCalculator.ts - NFPA 72 Battery Calculation Engine
 * Calculates battery requirements per NFPA 72 §27.6.2 requirements
 */

export interface BatteryCalcInput {
        devices: {
                type: string;
                standbyCurrent: number; // mA
                alarmCurrent: number; // mA
                count: number;
        }[];
        standbyHours: number; // default: 24
        alarmMinutes: number; // default: 5
        safetyFactor: number; // default: 1.2
}

interface BatteryCalcResult {
        devices?: {
                type: string;
                standbyCurrent: number; // mA
                alarmCurrent: number; // mA
                count: number;
        }[];
        totalStandbyCurrent: number; // A
        totalAlarmCurrent: number; // A
        requiredCapacity: number; // Ah
        recommendedBattery: {
                voltage: number; // 12V or 24V
                capacity: number; // Ah
                type: string; // "Lead Acid Sealed AGM"
        };
        compliance: {
                meetsNFPA27_6_2: boolean;
                standbyDuration: number; // hours
                alarmDuration: number; // minutes
                safetyFactor: number;
        };
}

interface ComplianceResult {
        compliant: boolean;
        violations: string[];
        warnings: string[];
}

/**
 * Calculates battery capacity requirements per NFPA 72
 * Formula: Battery Capacity = (Standby Current × Standby Hours) + (Alarm Current × Alarm Minutes/60)
 *
 * @param input Battery calculation parameters
 * @returns Battery calculation results
 */
export function calculateBatteryRequirements(
        input: BatteryCalcInput,
): BatteryCalcResult {
        // Calculate total standby current (convert mA to A)
        const totalStandbyCurrent = input.devices.reduce(
                (sum, device) => sum + (device.standbyCurrent * device.count) / 1000,
                0,
        );

        // Calculate total alarm current (convert mA to A)
        const totalAlarmCurrent = input.devices.reduce(
                (sum, device) => sum + (device.alarmCurrent * device.count) / 1000,
                0,
        );

        // Calculate required capacity per NFPA 72 §27.6.2
        // Capacity = (Standby Current × Standby Hours) + (Alarm Current × Alarm Minutes/60)
        const baseCapacity =
                totalStandbyCurrent * input.standbyHours +
                (totalAlarmCurrent * input.alarmMinutes) / 60;

        // Apply safety factor
        const requiredCapacity = baseCapacity * input.safetyFactor;

        // Recommend battery based on calculated capacity
        const recommendedBattery = {
                voltage: 24, // Default to 24V for larger systems
                capacity: Math.ceil(requiredCapacity / 2) * 2, // Round to nearest even number
                type: "Lead Acid Sealed AGM",
        };

        // Adjust voltage based on capacity if needed
        if (requiredCapacity < 20) {
                recommendedBattery.voltage = 12;
                recommendedBattery.capacity = Math.ceil(requiredCapacity);
        } else if (requiredCapacity > 100) {
                recommendedBattery.voltage = 24;
                recommendedBattery.capacity = Math.ceil(requiredCapacity / 2) * 2;
        }

        const meetsNFPA27_6_2 = input.standbyHours >= 24 && input.alarmMinutes >= 5;

        return {
                devices: input.devices,
                totalStandbyCurrent: Number.parseFloat(totalStandbyCurrent.toFixed(2)),
                totalAlarmCurrent: Number.parseFloat(totalAlarmCurrent.toFixed(2)),
                requiredCapacity: Number.parseFloat(requiredCapacity.toFixed(2)),
                recommendedBattery,
                compliance: {
                        meetsNFPA27_6_2,
                        standbyDuration: input.standbyHours,
                        alarmDuration: input.alarmMinutes,
                        safetyFactor: input.safetyFactor,
                },
        };
}

/**
 * Generate battery calculation report
 */
export function generateBatteryReport(result: BatteryCalcResult): string {
        let report = "";
        report += "═══════════════════════════════════════════════════\n";
        report += "       NFPA 72 BATTERY CALCULATION REPORT\n";
        report += "═══════════════════════════════════════════════════\n\n";

        report += "DEVICE BREAKDOWN:\n";
        report += "─────────────────────────────────────────────────\n";
        report += "Type              Count   Standby(mA)   Alarm(mA)\n";
        report += "─────────────────────────────────────────────────\n";

        const labelMap: Record<string, string> = {
                smoke: "Smoke Detector",
                heat: "Heat Detector",
                pull: "Pull Station",
                horn: "Horn/Strobe",
        };

        // F-02 FIX (Engineering Review): the previous code fell back to a
        // hardcoded fake device list (24 smoke + 8 heat + 12 pull + 16 horn)
        // whenever `result.devices` was empty. This fabricated device list
        // would appear in the printed report and silently mask the fact that
        // no devices had actually been provided — producing a misleading
        // "compliant" battery calculation for a design that had no devices.
        // Now: if no devices are present, we emit a prominent "NO DEVICES
        // PROVIDED" warning block instead of fabricating numbers.
        const devices = result.devices || [];
        if (devices.length === 0) {
                report += "⚠️  NO DEVICES PROVIDED\n";
                report += "─────────────────────────────────────────────────\n";
                report += "Battery calculation cannot be performed without a\n";
                report += "device list. Please call calculateBatteryRequirements()\n";
                report += "with a non-empty `devices` array and regenerate this\n";
                report += "report. The compliance verdict below is INVALID until\n";
                report += "real device data is supplied.\n\n";
        }

        for (const device of devices) {
                const typeLabel = labelMap[device.type.toLowerCase()] || device.type;
                const typeName = typeLabel.charAt(0).toUpperCase() + typeLabel.slice(1);
                const typeStr = typeName.padEnd(18).substring(0, 18);
                const countStr = device.count.toString().padEnd(8);
                const standbyStr = device.standbyCurrent.toString().padEnd(14);
                const alarmStr = device.alarmCurrent.toString();
                report += `${typeStr}${countStr}${standbyStr}${alarmStr}\n`;
        }
        report += "─────────────────────────────────────────────────\n\n";

        report += "CALCULATION:\n";
        report += "─────────────────────────────────────────────────\n";
        report += `Total Standby Current:     ${result.totalStandbyCurrent} A\n`;
        report += `Total Alarm Current:       ${result.totalAlarmCurrent} A\n`;
        report += `Standby Duration:          ${result.compliance.standbyDuration} hours\n`;
        report += `Alarm Duration:            ${result.compliance.alarmDuration} minutes\n`;
        report += `Safety Factor:             ${result.compliance.safetyFactor}x\n\n`;

        report += "RESULT:\n";
        report += "─────────────────────────────────────────────────\n";
        report += `Required Capacity:          ${result.requiredCapacity} Ah\n`;
        report += `Recommended Battery:        ${result.recommendedBattery.voltage}V ${result.recommendedBattery.capacity}Ah\n`;
        report += `                          (${result.recommendedBattery.type})\n\n`;

        report += "COMPLIANCE:\n";
        report += "─────────────────────────────────────────────────\n";
        if (result.compliance.meetsNFPA27_6_2) {
                report += `✅ PASSED - NFPA 72 §27.6.2 Compliant\n`;
        } else {
                report += `❌ FAILED - Does not meet NFPA 72 §27.6.2 requirements\n`;
        }
        report += `NFPA 72 §27.6.2 Battery Calculation Standard\n`;
        report += `Minimum 24 hours standby, 5 minutes alarm\n`;

        return report;
}

/**
 * Validate battery compliance per NFPA 72 §27.6.2
 */
export function validateBatteryCompliance(
        result: BatteryCalcResult,
): ComplianceResult {
        const violations: string[] = [];
        const warnings: string[] = [];

        // Check minimum standby duration (24 hours)
        if (result.compliance.standbyDuration < 24) {
                violations.push(
                        `Standby duration ${result.compliance.standbyDuration} hours does not meet minimum 24 hours per NFPA 72 §27.6.2`,
                );
        }

        // Check minimum alarm duration (5 minutes)
        if (result.compliance.alarmDuration < 5) {
                violations.push(
                        `Alarm duration ${result.compliance.alarmDuration} minutes does not meet minimum 5 minutes per NFPA 72 §27.6.2`,
                );
        }

        // Check safety factor
        if (result.compliance.safetyFactor < 1.2) {
                warnings.push(
                        `Safety factor ${result.compliance.safetyFactor}x is less than recommended 1.2x per NFPA 72 §27.6.2`,
                );
        }

        return {
                compliant: violations.length === 0,
                violations,
                warnings,
        };
}

/**
 * Get NFPA 72 §27.6.2 specific requirements
 */
export function getNFPA27_6_2Requirements(): string[] {
        return [
                "Minimum 24 hours of standby operation",
                "Minimum 5 minutes of alarm operation",
                "Battery capacity calculation: (Standby Current × Hours) + (Alarm Current × Minutes/60)",
                "Recommended 20% safety factor (1.2x)",
                "Batteries shall be rechargeable",
                "Voltage depression during alarm condition shall not exceed 20%",
                "Battery capacity shall be verified annually",
                "NFPA 72 §27.6.2 - Emergency Control Equipment and Firefighter’s Emergency Equipment",
        ];
}
