#!/bin/bash
# Weekly scraper for Denver Recreation Center schedules
# Runs every Sunday to capture the new week's schedule

# Set up logging
LOG_DIR="/Users/dustinwicker/projects/denver_rec_centers/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/scrape_$(date +%Y%m%d_%H%M%S).log"

# Project directory
PROJECT_DIR="/Users/dustinwicker/projects/denver_rec_centers"
SRC_DIR="$PROJECT_DIR/src"

echo "=== Weekly Scrape Started: $(date) ===" | tee -a "$LOG_FILE"

# Change to project directory
cd "$PROJECT_DIR" || exit 1

# Activate virtual environment if you have one (uncomment if needed)
# source venv/bin/activate

# Run the scraper
echo "Running scraper..." | tee -a "$LOG_FILE"
cd "$SRC_DIR"
python3 scrape_schedule.py --current-only 2>&1 | tee -a "$LOG_FILE"

# Check if scraper succeeded
if [ $? -eq 0 ]; then
    echo "Scraper completed successfully" | tee -a "$LOG_FILE"
    
    # Git operations
    cd "$PROJECT_DIR"
    
    # Add new/modified data files
    git add data/*.json 2>&1 | tee -a "$LOG_FILE"
    
    # Check if there are changes to commit
    if git diff --staged --quiet; then
        echo "No changes to commit" | tee -a "$LOG_FILE"
    else
        # Commit with date in message
        WEEK_DATE=$(date +%Y-%m-%d)
        git commit -m "Weekly schedule update: $WEEK_DATE" 2>&1 | tee -a "$LOG_FILE"
        
        # Push to GitHub
        echo "Pushing to GitHub..." | tee -a "$LOG_FILE"
        git push 2>&1 | tee -a "$LOG_FILE"
        
        if [ $? -eq 0 ]; then
            echo "Successfully pushed to GitHub" | tee -a "$LOG_FILE"
        else
            echo "ERROR: Failed to push to GitHub" | tee -a "$LOG_FILE"
        fi
    fi
else
    echo "ERROR: Scraper failed" | tee -a "$LOG_FILE"
fi

echo "=== Weekly Scrape Finished: $(date) ===" | tee -a "$LOG_FILE"

# Keep only last 10 log files
cd "$LOG_DIR"
ls -t scrape_*.log | tail -n +11 | xargs -r rm --

echo "Log saved to: $LOG_FILE"

