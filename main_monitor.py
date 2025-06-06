import asyncio
from check_brightness import check_brightness
from check_cabinet import check_cabinet
from check_modules import check_modules
from check_receiving_card import check_receiving_card
from check_receiving_cards_temperature import check_receiving_cards_temperature
from check_dvi import check_dvi
from base_monitoring import base
import time
base_script = base()
async def main():
    await base_script.initialize_program()
    i=0
    expected_modules = base_script.config['modules']
    total_receiver_cards = base_script.config_panel["receiver_cards"]
    total_lan_ports = base_script.config_panel["lan_ports"]   #Validate device found on player
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
            check_brightness() # This function will be called for each serial port found. and will handle the monitoring of brightness for each sender card.
            check_dvi() # This function will be called for each serial port found. and will handle the monitoring of DVI signal for each sender card.
            # loop through each LAN port to check for receiver cards
            for lan_value in range(total_lan_ports):
                # Check if the receiver card is connected before proceeding, a time sleep is added to ensure the serial port is ready! (testing shows that the serial port is not ready immediately after closing it manually and reopening it)
                if not base_script.ser.is_open:
                    time.sleep(0.05)
                    base_script.ser.open()                    
                no_of_receiver_cards = 0
                receiver_card_found = True
                while receiver_card_found:                    
                    # Check if receiver card is connected before proceeding
                    if not base_script.get_receiver_connected(base_script.ser.port, no_of_receiver_cards, lan_value):
                        base_script.ser.close()
                        break 
                    base_script.logger.info ("Connecting to receiver number: {}".format(no_of_receiver_cards+1))  
                    check_receiving_cards_temperature(base_script.ser, no_of_receiver_cards, lan_value) # This function will be called for each serial port found. and will handle the monitoring of receiving cards temperature.
                    check_modules(no_of_receiver_cards, lan_value) # This function will be called for each serial port found. and will handle the monitoring of modules.   
                    total_receiver_cards_found += 1 # Incrementing the total receiver cards found since we are checking for receiving cards in modules and temperature and 
                    no_of_receiver_cards += 1                     
        except Exception as e:
            base_script.logger.error(f"Error connecting to device on port {base_script.serial_port}: {e}")
        finally:
            base_script.ser.close()  # Closing 
            base_script.logger.info("Writing to JSON file")
main()        