# ---------------------------------------------------------------------------------------
# This script is used to create and/or update Windows Task Scheduler to run the auto
# brightness adjust script at set times. Current times for tasks are: Sunset, Sunrise
# Dusk, and Dawn. 


import win32com.client
import datetime
from astral import LocationInfo
from astral.sun import sun
import requests
import json
from pathlib import Path
import os
import logging
from logging.handlers import TimedRotatingFileHandler
import methods
import sys

# LOGGER
FORMATTER = logging.Formatter('%(asctime)s %(name)s %(levelname)-8s %(message)s', datefmt='%d/%m/%Y %H:%M:%S')
SCRIPT_DIR = Path(__file__).parent.resolve()
LOG_FILE = str(SCRIPT_DIR / "debug.log")  # Convert Path object to string
LOGGER_NAME = 'display_status'
LOGGER_SCHEDULE = 'midnight'
LOGGER_BACKUPS = 7
LOGGER_INTERVAL = 1

# Flags
error_flag = False


def main():
    global error_flag
    my_logger = methods.get_logger(LOGGER_NAME,LOG_FILE,FORMATTER,LOGGER_SCHEDULE,LOGGER_INTERVAL,LOGGER_BACKUPS) # Set up the logging

    try:
        # Get the current script path and the brightness adjustment script path
        this_script = Path(__file__).resolve()
        auto_brightness_script = str(Path(__file__).parent / "automatic_brightness_adjustment.py")

        # Retrieve location details
        location = get_location()
        my_logger.debug("Location details:", location)

        # Get sunset/sunrise information
        city = LocationInfo(location["city"], location["region"], location["timezone"],
                            float(location["latitude"]), float(location["longitude"]))
        today = datetime.date.today()
        sun_times = sun(city.observer, date=today)

        # Format times
        sun_data = {key: value.isoformat() for key, value in sun_times.items()}
        
        # Force dawn to be 05:00:00 UTC
        #dawn_fixed = datetime.datetime.combine(today, datetime.time(5, 0, 0), datetime.timezone.utc)
        #sun_data["dawn"] = dawn_fixed.isoformat()

        my_logger.info(f"Sun times: {sun_data}")

        # Write sun data to file (update the file with new sun data)
        write_to_file({"sun_times": sun_data})

        # Check if the one-time task to run this script daily exists
        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        root_folder = scheduler.GetFolder("\\")

        off_time = datetime.datetime.now().replace(hour=1, minute=0, second=0, microsecond=0).isoformat()
        on_time = datetime.datetime.now().replace(hour=5, minute=0, second=0, microsecond=0).isoformat()


        try:
            task = root_folder.GetTask("Retrieve Daylight Information")
            my_logger.info("Task 'Retrieve Daylight Information' already exists. Skipping creation.")
        except Exception:
            my_logger.info("Task 'Retrieve Daylight Information' does not exist. Creating it now.")
            # Generate today's date with the desired time (10:00 AM) in ISO format
            todays_date = datetime.datetime.now().date()
            run_time = f"{todays_date}T00:00:01"
            create_or_update_daily_task_specific_times("Retrieve Daylight Information", this_script, run_time)

        # Create tasks for sunrise and sunset
        create_or_update_daily_task_specific_times("Brightness OFF", auto_brightness_script, off_time)
        create_or_update_daily_task_specific_times("Brightness ON", auto_brightness_script, on_time)
        create_or_update_daily_task_specific_times("Sunset Auto Brightness", auto_brightness_script, sun_data["sunset"])
        create_or_update_daily_task_specific_times("Dawn Auto Brightness", auto_brightness_script, sun_data["dawn"])

    except Exception as e:
        error_flag = True
        my_logger.error(f"An error occurred: {e}")

    if (error_flag == True):
        my_logger.error("An error has been detected - Error flag is to be written to JSON")
        write_to_file({"error_flag": error_flag})


def create_or_update_daily_task_specific_times(task_name, auto_brightness_script, set_time):
    global error_flag

    logger = logging.getLogger(LOGGER_NAME)

    TriggerTypeDaily = 2 #Daily Trigger
    OneDayInterval = 1

    scheduler = win32com.client.Dispatch("Schedule.Service")
    scheduler.Connect()
    root_folder = scheduler.GetFolder("\\")
    try:
        try:
            # Try to retrieve the task by name
            task = root_folder.GetTask(task_name)
            return  # Exit since the task already exists
        except Exception as e:
            # If task does not exist, we can create it
            definition = scheduler.NewTask(0)  # Create a new task definition
        
        # Clear existing triggers
        definition.Triggers.Clear()

        trigger = definition.Triggers.Create(TriggerTypeDaily) 
        trigger.DaysInterval = OneDayInterval  
        trigger.StartBoundary = set_time

        # Set the action to run the Python script
        definition.Actions.Clear()
        action = definition.Actions.Create(0)  # TASK_ACTION_EXEC
        python_path = sys.executable
        action.Path = f'"{python_path}"'
        action.Arguments = f'"{auto_brightness_script}"'

        # Set task properties
        definition.RegistrationInfo.Description = f"Run {auto_brightness_script} at specified times."
        definition.Principal.LogonType = 3  # TASK_LOGON_INTERACTIVE_TOKEN
        # The following is to run the task when the user is not logged in
        # definition.Principal.LogonType = 3  # TASK_LOGON_INTERACTIVE_TOKEN
        definition.Settings.Enabled = True
        definition.Settings.AllowDemandStart = True
        definition.Settings.StartWhenAvailable = True

        # To be added based on NUC login
        #username = "YourUsername"  
        #password = "YourPassword"  

        # Set the task to wake the computer to run the task
        definition.Settings.WakeToRun = True

        # Set the task to restart after 1 minute if it fails (max of 3 retries)
        definition.Settings.RestartInterval = "PT1M"  # 1 minute
        definition.Settings.RestartCount = 3  # Max 3 retries on failure

        root_folder.RegisterTaskDefinition(f"{task_name} Trigger", definition, 6, None, None, 0)

        logger.info(f"Task '{task_name}' updated/created successfully to run at: {(set_time)}.")
    except Exception as e:
        logger.error(f"Failed to create or update task '{task_name}'. Error: {e}")
        error_flag = True

# ---------------------------------------------------------------------------------------
# get_location
# Retrieves location data using the ipaddress. Data is stored in a dictionary: city, region, 
# timezone, lattitude, and longitude.
#   INPUT:      NONE
#   RETURNS:    data struct - location dictionary (city, region, 
#               timezone, lattitude, and longitude)           
#           
#

def get_location(cache_file="config.json"):
    global error_flag
    logger = logging.getLogger(LOGGER_NAME)

    # Get the directory of the current script
    script_dir = Path(__file__).parent.resolve()
    cache_path = script_dir / cache_file  # Ensure the file is in the script's directory

    # Check if the cache file exists and try to load it
    if cache_path.exists():
        try:
            with cache_path.open('r', encoding='utf-8') as file:
                cached_data = json.load(file)
                # Check if location data exists and has all required keys
                if "location" in cached_data:
                    location_data = cached_data["location"]
                    required_keys = ["city", "region", "timezone", "latitude", "longitude"]
                    if all(key in location_data for key in required_keys):
                        logger.debug(f"Loaded valid location data from cache: {location_data}")
                        return location_data
                logger.debug("Cache is missing required location keys. Fetching new location data...")
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"Error reading cache file: {e}. Proceeding to fetch location data...")

    # Fetch location data from ipinfo.io if no valid cache is found
    try:
        response = requests.get("https://ipinfo.io", timeout=5)
        response.raise_for_status()
        data = response.json()

        latlong = data.get("loc").split(",")
        location_data = {
            "city": data.get("city"),
            "region": data.get("region"),
            "timezone": data.get("timezone"),
            "latitude": latlong[0],
            "longitude": latlong[1]
        }

        # Save location data to daylight_times.json in the same script directory
        write_to_file({"location": location_data}, filename=str(cache_path), mode='w')

        return location_data

    except (requests.RequestException, ValueError) as e:
        logger.error(f"Failed to fetch location: {e}. Using default location: London")
        error_flag = True
        return {
            "city": "London",
            "region": "England",
            "timezone": "Europe/London",
            "latitude": "51.5085",
            "longitude": "-0.1257"
        }

# ---------------------------------------------------------------------------------------
# write_to_file
# Writes location data to a json file 
#   INPUT:      data - data to be written to the json file
#               filename - json file (default: daylight_times.json)        
#           
#
def write_to_file(data, filename="daylight_times.json", mode='w'):
    global error_flag

    logger = logging.getLogger(LOGGER_NAME)

    try:
        # Get the folder where the script is being run from
        script_dir = Path(__file__).parent.resolve()  
        filepath = script_dir / filename  # Save file in the script's directory

        # Ensure the directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Check if the file exists and read its content, if it's not empty
        if filepath.exists() and filepath.stat().st_size > 0:
            with filepath.open('r', encoding='utf-8') as file:
                existing_data = json.load(file)
        else:
            existing_data = {}

        # Update the existing data with the new data
        existing_data.update(data)

        # Write the combined data back to the file
        with filepath.open(mode, encoding='utf-8') as file:
            json.dump(existing_data, file, indent=4)

        logger.debug(f"Data successfully written to: {filepath}")
        logger.info(f"File saved in folder: {script_dir}")

    except Exception as e:
        logger.error(f"Error writing to file: {e}")
        error_flag = True
        raise


if __name__ == "__main__":
    main()

