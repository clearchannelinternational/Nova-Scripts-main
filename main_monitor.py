import asyncio
from check_brightness import check_brightness
# from check_cabinet import check_cabinet
from check_modules import check_modules
# from check_receiving_card import check_receiving_card
from check_receiving_cards_temperature import check_receiving_cards_temperature
from check_receiving_card import *
from check_dvi import check_dvi
from base_monitoring import base
import time, subprocess, datetime, sys, os
base_script = base()
async def main():
    username = os.environ.get("USERNAME")
    NOVA_PATH = rf"C:\Users\{username}\Desktop\MonitorSite.lnk"
    stop_nova_command = 'Stop-Process -Name NovaMonitorManager, MarsServerProvider -Force'
    start_nova_command = "".join(["Start-Process ",NOVA_PATH])
    process_nova_command = "".join(["Get-Process ","NovaMonitorManager"])  
    nova_started = not bool(subprocess.run(["Powershell","-Command", process_nova_command]).returncode) ;#get process for novamonitoringsite
    
    subprocess.run(["powershell", "-Command", stop_nova_command], shell=True)
    await base_script.initialize_program()
    i=0
    expected_modules = base_script.config['modules']
    expected_receiver_cards = base_script.config_panel["receiver_cards"]
    expected_ports = base_script.config_panel.get("lan_ports",4)   #Validate device found on player
    total_receiver_cards_found = 0
    for base_script.serial_port in sorted(base_script.valid_ports):
        i += 1
        base_script.logger.info("*******************    DEVICE {}   *******************".format(i))
        base_script.logger.info("Connecting to device on {}".format(base_script.serial_port))
        base_script.ser.port = base_script.serial_port 
        try:
            if base_script.ser.isOpen() == False:
                base_script.ser.open()
            base_script.ser.flushInput() #flush input buffer, discarding all its contents
            base_script.ser.flushOutput() #flush output buffer, aborting current output and discard all that is in buffer
            base_script.logger.info("Opened device on port: " + base_script.ser.name) # remove at production
            await check_brightness(base_script) # This function will be called for each serial port found. and will handle the monitoring of brightness for each sender card.
            await check_dvi(base_script) # This function will be called for each serial port found. and will handle the monitoring of DVI signal for each sender card.
            # loop through each LAN port to check for receiver cards
            valid_ports_found=0
            for lan_value in range(4):              
                if expected_ports == valid_ports_found:
                    break
                no_of_receiver_cards = 0
                receiver_card_found = True
                # Check if the receiver card is connected before proceeding, a time sleep is added to ensure the serial port is ready! (testing shows that the serial port is not ready immediately after closing it manually and reopening it)                
                if not base_script.ser.is_open:
                    time.sleep(0.05)
                    base_script.ser.open()                    
                while receiver_card_found:                    
                    # Check if receiver card is connected before proceeding
                    if not base_script.get_receiver_connected(base_script.ser.port, no_of_receiver_cards, lan_value):
                        base_script.ser.close()
                        break                    
                    base_script.logger.info ("Connected to receiver number: {}".format(no_of_receiver_cards+1))  
                    time.sleep(0.5)
                    await check_receiving_cards_temperature(base_script, no_of_receiver_cards, lan_value) # This function will be called for each serial port found. and will handle the monitoring of receiving cards temperature.
                    time.sleep(0.5)                    
                    await check_modules(base_script,no_of_receiver_cards, lan_value) # This function will be called for each serial port found. and will handle the monitoring of modules.   
                    total_receiver_cards_found += 1 # Incrementing the total receiver cards found since we are checking for receiving cards in modules and temperature and                                  
                    no_of_receiver_cards += 1  #no of receiver cards is used to pass the index of the actual connected receiver cards to the HEX check 
                    base_script.logger.debug(f"no of receiving  card for port {base_script.ser.port} LAN {lan_value} = {no_of_receiver_cards}")                                  
        except Exception as e:
            base_script.logger.error(f"Error connecting to device on port {base_script.serial_port}: {e}")
        finally:
            valid_ports_found += 1
            base_script.ser.close()  # Closing 
            base_script.logger.info("Writing to JSON file")
            base_script.logger.debug(f"Total cards found {total_receiver_cards_found}") 
    #check receivingcard
    check_receiving_cards(base_script, expected_receiver_cards, total_receiver_cards_found)
    # Start monitorsite 
    subprocess.run(["Powershell","-Command", start_nova_command], shell=True)
    # update task to run in 15 minutes
    subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", "C:\\LEDMonitoring\\task_scheduler_updater.ps1" ], shell=True)
asyncio.run(main())
