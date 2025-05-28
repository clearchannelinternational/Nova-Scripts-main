#!/usr/bin/env python3
import asyncio
from base_monitoring import *
base_script = base()
async def main(reader, writer):
   await base_script.initialize_program(reader, writer)
   exit_code = base_script.UNKNOWN
   monitor_message = "receiving_cards"
   total_receiver_cards = base_script.config_panel["receiver_cards"]
   total_lan_ports = base_script.config_panel["lan_ports"]   #Validate device found on player
   total_receiver_cards_found = 0
   if (base_script.device_found == 0):
      message = "NO DEVICE - make sure a valid controller is connected, that the correct baudrate is defined in config.json and ensure the NOVA LCT is not running on the host system \nThis can also mean that you don't run the tool as administrator"
      exit_code = base_script.CRITICAL
      base_script.logger.info ("EXIT CODE: {}, {}".format(exit_code, message))
      await base_script.monitoring_log_output(message,monitor_message, exit_code, reader, writer)
   
   #looping through each sender card found
   i=0
   for base_script.serial_port in sorted(base_script.valid_ports):
      base_script.logger.info("*******************    DEVICE {}   *******************".format(i))
      base_script.logger.info("Connecting to device on {}".format(base_script.serial_port))
      base_script.ser.port = base_script.serial_port      
      try: 
         if base_script.ser.isOpen() == False:
            base_script.ser.open()
         base_script.ser.flushInput() #flush input buffer, discarding all its contents
         base_script.ser.flushOutput() #flush output buffer, aborting current output and discard all that is in buffer
         base_script.logger.info("Opened device on port: " + base_script.ser.name) # remove at production
      except base_script.serialException as e:
         message = f"Error opening base_script.serial port: {base_script.ser.name} - {str(e)}"
         exit_code = base_script.CRITICAL
         base_script.logger.error(message)
         await base_script.monitoring_log_output(message,monitor_message, exit_code, reader, writer)
         
      # -------------------------------------
      # RETRIEVE PARAMETERS FROM SENDER CARDS
      # -------------------------------------
      receiver_card_found = True
      
      base_script.status[base_script.serial_port]["receiverCard"]={}
      display_on = True
      for lan_value in range(total_lan_ports):
         no_of_receiver_cards = 0
         if not base_script.ser.is_open:
            time.sleep(0.05)
            base_script.ser.open()
         while receiver_card_found != False: 
            base_script.logger.info("=============================================================================================================================================")
            base_script.logger.info ("Connecting to receiver number: {}".format(no_of_receiver_cards+1))    
            try:     
               if not get_receiver_connected(base_script.ser.port, no_of_receiver_cards,lan_value):
                  base_script.ser.close()
                  break
               no_of_receiver_cards += 1
               total_receiver_cards_found += 1
            except Exception as e:
               print("")
   if total_receiver_cards_found != total_receiver_cards: 
      message, exit_code = f"NO of receiver cards {total_receiver_cards_found} EXPECTED {total_receiver_cards}", base_script.CRITICAL
      base_script.logger.error(f"{monitor_message}=1")
      base_script.logger.error(f"receiving_cards_output={message}")
   else: 
      message, exit_code = f"NO of receiver cards {total_receiver_cards_found} EXPECTED {total_receiver_cards}", base_script.GOOD
      base_script.logger.info(f"{monitor_message}=0")
      base_script.logger.info(f"receiving_cards_output={message}")
   base_script.ser.close() #closing 
   base_script.logger.info("Writing to JSON file")
   
   # -------------------------------------------------------------
   # TO DO
   # Include checks for brightness >0. This should be a WARNING.
   # -------------------------------------------------------------

   base_script.logger.info ("EXIT CODE: {}, {}".format(exit_code, message))
   
   # ----------------------------------------------------------------
   # TO DO
   # Consider including exit_code and output message into base_script.status.json     
   # ----------------------------------------------------------------
   
   await base_script.monitoring_log_output(message,monitor_message, exit_code, reader, writer)    

def get_receiver_connected(port, receiver_index_value, lan_value):
# ---------------------------------------------------------------------------------------
# CHECK CONNECTION TO RECEIVER CARD
# ---------------------------------------------------------------------------------------   
   base_script.logger = logging.getLogger(base_script._logger_name)
   check_receiver_model [7] = lan_value
   check_receiver_model [8] = receiver_index_value
   check_receiver_model_send = methods.checksum (check_receiver_model)
   base_script.ser.write (check_receiver_model_send)
   time.sleep (1) 
   inWaiting = base_script.ser.inWaiting()
   if inWaiting>0:
      response = base_script.ser.read(size=inWaiting)
      rx_data = list(response)
      base_script.logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if base_script.check_response(rx_data):
         receiver_card_found = True
      else:
         receiver_card_found = False          
   else:
      base_script.logger.warning("No data available at the input buffer")
      receiver_card_found = False
   return receiver_card_found
