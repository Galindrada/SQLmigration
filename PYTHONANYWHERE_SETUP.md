# PythonAnywhere Scheduled Market Activity Setup

## Overview
Since PythonAnywhere doesn't support cron jobs, we've created alternative solutions for automated market activity.

## Option 1: PythonAnywhere Scheduled Tasks (Recommended)

### Step 1: Upload the web script
1. Upload `web_scheduled_market_activity.py` to your PythonAnywhere account
2. Make it executable: `chmod +x web_scheduled_market_activity.py`

### Step 2: Set up scheduled tasks
1. Go to your PythonAnywhere dashboard
2. Click on "Tasks" tab
3. Click "Create a new task"
4. Set the command to: `python3 /home/yourusername/web_scheduled_market_activity.py`
5. Set the schedule (e.g., every 4 hours: `0 */4 * * *`)
6. Save the task

### Step 3: Monitor the task
- Check the "Tasks" tab for execution logs
- Look for success/failure messages
- Adjust schedule as needed

## Option 2: Web Hook (Alternative)

### Step 1: Use the web hook endpoint
- URL: `https://yourusername.pythonanywhere.com/webhook/scheduled_market_activity`
- Method: POST
- No authentication required (you can add a secret key if needed)

### Step 2: Set up external scheduling
You can use external services to call this web hook:
- **UptimeRobot**: Free service that can make HTTP requests on a schedule
- **Cron-job.org**: Free online cron service
- **Zapier**: Automation service with scheduling
- **IFTTT**: If This Then That automation

### Step 3: Configure external service
1. Create an account with your chosen service
2. Set up a scheduled task to make a POST request to your web hook URL
3. Set the frequency (e.g., every 4 hours)
4. Monitor the service for success/failure

## Option 3: Manual Trigger (Always Available)

### Via Tools Page
1. Go to your application's Tools page
2. Click "🔄 Trigger Market Activity" button
3. Runs immediately

### Via Direct URL
- URL: `https://yourusername.pythonanywhere.com/tools/scheduled_market_activity`
- Method: POST
- Requires login

## What the Scheduled Activity Does

1. **CPU AI Activity**: Triggers CPU teams to make transfer decisions
2. **Expired Offers Processing**: Cleans up expired free agent offers
3. **Blog Post Generation**: Creates a blog post about the activity
4. **Market Updates**: Processes all pending transactions

## Monitoring

### Check Blog Posts
- Look for "🔄 Scheduled Market Activity Complete" posts
- These indicate successful execution

### Check Logs
- PythonAnywhere Tasks tab shows execution logs
- Application logs show any errors

### Check Market Activity
- CPU teams should be making transfers
- Expired offers should be processed
- Market bazaar should be active

## Troubleshooting

### Common Issues
1. **Import Errors**: Make sure all files are in the same directory
2. **Database Errors**: Check database permissions
3. **Memory Issues**: PythonAnywhere free accounts have memory limits

### Solutions
1. **Restart Web App**: If imports fail, restart your web app
2. **Check File Permissions**: Ensure scripts are executable
3. **Monitor Resource Usage**: Check CPU and memory usage

## Recommended Schedule

- **Every 4 hours**: `0 */4 * * *` (good balance)
- **Every 6 hours**: `0 */6 * * *` (less frequent)
- **Every 8 hours**: `0 */8 * * *` (minimal activity)
- **Daily at 2 AM**: `0 2 * * *` (once per day)

## Security Notes

- The web hook endpoint is currently open (no authentication)
- Consider adding a secret key for production use
- Monitor for abuse or excessive requests

## Success Indicators

✅ Blog posts appear regularly
✅ CPU teams make transfers
✅ Expired offers are processed
✅ Market bazaar shows activity
✅ No error messages in logs
