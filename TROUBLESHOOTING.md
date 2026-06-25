# FireAI Troubleshooting Guide

This guide provides solutions to common issues encountered when using FireAI. Since FireAI is a safety-critical system, pay special attention to any issues that could affect safety calculations.

## 🚨 Emergency Procedures

### Immediate Safety Concerns
If you encounter any behavior that could compromise fire protection safety:

1. **Stop using the system immediately**
2. **Verify all calculations manually**
3. **Contact the FireAI team at [emergency@fireai.org](mailto:emergency@fireai.org)**
4. **Do not rely on potentially compromised results**

## 🔧 Common Installation Issues

### Virtual Environment Setup
**Problem**: Installation fails with permission errors
**Solution**: 
```bash
# Ensure you're using a virtual environment
python -m venv fireai_env
source fireai_env/bin/activate  # On Windows: fireai_env\Scripts\activate
pip install fireai
```

### Missing Dependencies
**Problem**: ImportError for required packages
**Solution**:
```bash
# Update pip first
pip install --upgrade pip

# Install with all dependencies
pip install fireai[all]

# Or install missing packages individually
pip install shapely numpy scipy
```

### CAD File Compatibility
**Problem**: CAD files fail to load or parse incorrectly
**Solution**:
1. Verify the file format is supported (DWG, DXF, RVT, IFC)
2. Check that the file is not corrupted
3. Ensure CAD file doesn't contain unsupported elements
4. Try simplifying the CAD file if it's very complex

## ⚙️ Configuration Issues

### Environment Variables
**Problem**: Configuration errors or missing settings
**Solution**: Create a `.env` file in your project root:
```env
FIREAI_DEBUG=false
FIREAI_LOG_LEVEL=INFO
FIREAI_DATA_DIR=./data
FIREAI_CACHE_DIR=./cache
FIREAI_MAX_MEMORY_GB=8
FIREAI_TIMEOUT_SECONDS=300
```

### API Connection Issues
**Problem**: Cannot connect to FireAI API
**Solution**:
1. Check that the server is running: `fireai-server --host 0.0.0.0 --port 8000`
2. Verify the correct endpoint URL
3. Check firewall settings
4. Ensure authentication tokens are valid

## 🧮 Calculation Issues

### Detector Placement Problems
**Problem**: Detectors not placed optimally or coverage gaps exist
**Solution**:
1. Verify room geometry is valid and closed polygons
2. Check that all required parameters are specified
3. Review building type classification (affects NFPA rules)
4. Validate that coverage radius matches detector type

### Compliance Checking Failures
**Problem**: False positives or negatives in compliance checking
**Solution**:
1. Verify building codes and standards are correctly selected
2. Check that local amendments are applied
3. Review calculation tolerances and safety margins
4. Manually verify critical compliance points

### Performance Issues
**Problem**: Slow calculations or memory exhaustion
**Solution**:
1. Simplify CAD geometry where possible
2. Increase available memory allocation
3. Process large files in smaller sections
4. Check for circular dependencies in geometry

## 🚨 Safety-Related Issues

### Coverage Calculation Discrepancies
**Problem**: Coverage calculations don't match manual calculations
**Solution**:
1. **Always verify critical calculations manually**
2. Check units (meters vs feet)
3. Verify detector specifications are correct
4. Validate room boundary definitions
5. Contact support if discrepancy exceeds 1%

### False Compliance Reports
**Problem**: System reports compliance when violations exist
**Solution**:
1. **Immediately stop relying on automated reports**
2. Perform manual compliance verification
3. Report the issue to the FireAI team immediately
4. Document the specific violation that wasn't caught

### Missing Safety Checks
**Problem**: Safety validations appear to be bypassed
**Solution**:
1. **Verify all safety features are enabled**
2. Check that safety level is set to maximum
3. Review configuration for any disabled safety features
4. Contact support immediately if safety features are missing

## 🔍 Debugging Tips

### Enable Detailed Logging
```bash
# Set log level to DEBUG for detailed output
export FIREAI_LOG_LEVEL=DEBUG
fireai-cli --verbose analyze building.dxf
```

### Diagnostic Commands
```bash
# Check system health
fireai-cli diagnose

# Validate CAD file
fireai-cli validate-cad building.dxf

# Check compliance rules
fireai-cli list-rules

# Test calculations
fireai-cli test-calculations
```

### Safety Verification
```bash
# Run safety audit on results
fireai-cli safety-audit results.json

# Verify compliance independently
fireai-cli verify-compliance results.json
```

## 📋 Error Reference

### Common Error Codes
- `FAC-001`: Invalid geometry - Check CAD file validity
- `FAC-002`: Insufficient coverage - Add more detectors or adjust placement
- `FAC-003`: Compliance violation - Review building codes
- `FAC-004`: Resource exhaustion - Simplify model or increase resources
- `FAC-005`: Safety gate failure - Check safety configuration

### Warning Levels
- **CRITICAL**: Stop immediately, safety may be compromised
- **HIGH**: Verify manually, may affect safety
- **MEDIUM**: Review results carefully
- **LOW**: Minor issue, safe to continue

## 🆘 Getting Help

### When to Contact Support
- Safety-related concerns
- Compliance checking failures
- Unexpected calculation results
- Security vulnerabilities
- Performance issues with safety-critical systems

### Support Channels
- **Emergency (Safety)**: [emergency@fireai.org](mailto:emergency@fireai.org) (24/7)
- **Technical Issues**: [support@fireai.org](mailto:support@fireai.org) (Business hours)
- **Feature Requests**: [features@fireai.org](mailto:features@fireai.org)
- **Security Issues**: [security@fireai.org](mailto:security@fireai.org)

### Information to Include
When contacting support, include:
- FireAI version
- Python version
- Operating system
- Detailed error message
- Steps to reproduce
- CAD file sample (if possible)
- Expected vs. actual results

## 🧪 Testing Your Installation

### Basic Functionality Test
```bash
# Verify installation
python -c "import fireai; print(fireai.__version__)"

# Run basic test
fireai-cli test

# Validate environment
fireai-cli check-env
```

### Safety System Test
```bash
# Run safety validation
fireai-cli safety-check

# Verify compliance engine
fireai-cli test-compliance
```

## ⚠️ Important Safety Reminders

1. **FireAI is a tool to assist professional engineers, not replace them**
2. **Always have designs reviewed by licensed professionals**
3. **Verify critical calculations independently**
4. **Stay updated with the latest safety patches**
5. **Report any safety-related issues immediately**

---

**If you encounter any issue that might affect safety, do not continue using the system until the issue is resolved. When in doubt, consult with a licensed fire protection engineer.**

For urgent safety concerns, contact emergency services and the FireAI team immediately.