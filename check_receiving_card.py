#!/usr/bin/env python3
from base_monitoring import *
async def main(reader, writer):
   global sleep_time
   global flash_wait_time
   global status 
   global last_updated
   global data
   global logger
   global config
   global device_found, valid_ports, ser
   monitor_message = "receiving_cards"
   exit_code = UNKNOWN
   initialize_program(reader, writer)
   total_receiver_cards = config_panel["receiving_cards"]
   total_lan_ports = config_panel["lan_ports"]   #Validate device found on player
   if (device_found == 0):
      message = "NO DEVICE - make sure a valid controller is connected, that the correct baudrate is defined in config.json and ensure the NOVA LCT is not running on the host system \nThis can also mean that you don't run the tool as administrator"
      exit_code = CRITICAL
      logger.info ("EXIT CODE: {}, {}".format(exit_code, message))
      end_time = time.time()
      
      await monitoring_log_output(message,monitor_message, exit_code, reader, writer)
   
   #looping through each sender card found
   i=0
   for serial_port in sorted(valid_ports):
      logger.info("*******************    DEVICE {}   *******************".format(i))
      logger.info("Connecting to device on {}".format(serial_port))
      ser.port = serial_port      
      try: 
         if ser.isOpen() == False:
            ser.open()
         ser.flushInput() #flush input buffer, discarding all its contents
         ser.flushOutput() #flush output buffer, aborting current output and discard all that is in buffer
         logger.info("Opened device on port: " + ser.name) # remove at production
      except SerialException as e:
         message = f"Error opening serial port: {ser.name} - {str(e)}"
         exit_code = CRITICAL
         logger.error(message)
         await monitoring_log_output(message,monitor_message, exit_code, reader, writer)
         
      # -------------------------------------
      # RETRIEVE PARAMETERS FROM SENDER CARDS
      # -------------------------------------
      receiver_card_found = True
      total_receiver_cards_found = 0
      status[serial_port]["receiverCard"]={}
      display_on = True
      for lan_value in range(total_lan_ports):
         no_of_receiver_cards = 0
         if not ser.is_open:
            time.sleep(0.05)
            ser.open()
         while receiver_card_found != False: 
            logger.info("=============================================================================================================================================")
            logger.info ("Connecting to receiver number: {}".format(no_of_receiver_cards+1))    
            try:     
               if not get_receiver_connected(ser.port, no_of_receiver_cards,lan_value):                  
                  ser.close()
                  break
               no_of_receiver_cards += 1
               total_receiver_cards_found += 1
            except Exception as e:
               print(f"no receiving card found {no_of_receiver_cards}")
           
   if total_receiver_cards_found != total_receiver_cards: message, exit_code = f"NO of receiver cards {no_of_receiver_cards} EXPECTED {total_receiver_cards}", CRITICAL
   else: message, exit_code = f"NO of receiver cards {total_receiver_cards_found} EXPECTED {total_receiver_cards}", GOOD
   ser.close() #closing 
   logger.info("Writing to JSON file")
   
   # -------------------------------------------------------------
   # TO DO
   # Include checks for brightness >0. This should be a WARNING.
   # -------------------------------------------------------------

   logger.info ("EXIT CODE: {}, {}".format(exit_code, message))
   
   # ----------------------------------------------------------------
   # TO DO
   # Consider including exit_code and output message into status.json     
   # ----------------------------------------------------------------
   
   await monitoring_log_output(message, monitor_message, exit_code, reader, writer)    

def get_receiver_connected(port, receiver_index_value, lan_value):
# ---------------------------------------------------------------------------------------
# CHECK CONNECTION TO RECEIVER CARD
# ---------------------------------------------------------------------------------------   
   logger = logging.getLogger(LOGGER_NAME)
   check_receiver_model [7] = lan_value
   check_receiver_model [8] = receiver_index_value
   check_receiver_model_send = methods.checksum (check_receiver_model)
   ser.write (check_receiver_model_send)
   time.sleep (sleep_time)
   inWaiting = ser.inWaiting()
   if inWaiting>0:
      response = ser.read(size=inWaiting)
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         receiver_card_found = True
      else:
         receiver_card_found = False          
   else:
      logger.warning("No data available at the input buffer")
      receiver_card_found = False
   return receiver_card_found
# ------------------------------------------------------------------------------------------------------------
# PROGRAM ENTRY POINT - this won't be run only when imported from external module
# ------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
   try:      
      asyncio.run(communicate_with_server())
   except KeyboardInterrupt:
      logger.info("Client shut down manually.")
      sys.exit(UNKNOWN)
   except Exception as e:
      logger.exception(f"Client encountered an error: {e}")
      sys.exit(UNKNOWN)