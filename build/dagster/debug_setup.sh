#!/bin/bash

echo "=== Debugging Dagster Setup ==="
echo ""

echo "Current directory: $(pwd)"
echo "PYTHONPATH: $PYTHONPATH"
echo ""

echo "=== Checking directory structure ==="
if [ -d "/app/src/dagster_quickstart" ]; then
    echo "✅ Directory /app/src/dagster_quickstart exists"
    echo "Contents:"
    ls -la /app/src/dagster_quickstart
else
    echo "❌ Directory /app/src/dagster_quickstart does not exist"
    echo "Creating directory structure..."
    mkdir -p /app/src/dagster_quickstart
fi

echo ""
echo "=== Checking Python imports ==="
python3 -c "
import sys
print('Python sys.path:')
for p in sys.path:
    print(f'  - {p}')

print('')
print('Attempting to import the module:')
try:
    import src.dagster_quickstart
    print('✅ Module src.dagster_quickstart imported successfully')
    print(f'Module location: {src.dagster_quickstart.__file__}')
    print('Module contents:')
    print(dir(src.dagster_quickstart))
    print('')
    print('Checking for defs object:')
    if hasattr(src.dagster_quickstart, 'defs'):
        print('✅ defs object found')
        print(f'Type: {type(src.dagster_quickstart.defs)}')
    else:
        print('❌ defs object not found')
except ImportError as e:
    print(f'❌ Import error: {e}')
except Exception as e:
    print(f'❌ Other error: {e}')
"

echo ""
echo "=== Checking workspace.yaml ==="
if [ -f "/app/src/dagster_quickstart/workspace.yaml" ]; then
    echo "✅ workspace.yaml exists"
    echo "Contents:"
    cat /app/src/dagster_quickstart/workspace.yaml
else
    echo "❌ workspace.yaml does not exist"
fi

echo ""
echo "=== Debug complete ===" 