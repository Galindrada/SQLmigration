#!/bin/bash

# Setup cron job for scheduled market activity
# This script sets up a cron job to run market activity every 4 hours

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/scheduled_market_activity.py"
LOG_FILE="$SCRIPT_DIR/market_activity.log"

echo "Setting up cron job for scheduled market activity..."

# Make the Python script executable
chmod +x "$PYTHON_SCRIPT"

# Create the cron job entry (every 4 hours)
CRON_ENTRY="0 */4 * * * cd $SCRIPT_DIR && python3 $PYTHON_SCRIPT >> $LOG_FILE 2>&1"

# Add to crontab
(crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -

echo "✅ Cron job added successfully!"
echo "📅 Market activity will run every 4 hours"
echo "📝 Logs will be written to: $LOG_FILE"
echo ""
echo "To view current cron jobs: crontab -l"
echo "To remove the cron job: crontab -e (then delete the line)"
echo ""
echo "Alternative cron schedules:"
echo "  Every 2 hours: 0 */2 * * *"
echo "  Every 6 hours: 0 */6 * * *"
echo "  Every 8 hours: 0 */8 * * *"
echo "  Daily at 2 AM: 0 2 * * *"
echo "  Daily at 6 AM: 0 6 * * *"
echo "  Daily at 12 PM: 0 12 * * *"
echo "  Daily at 6 PM: 0 18 * * *"
