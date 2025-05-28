
#!/usr/bin/env python3
import asyncio
from base_monitoring import *
base_script = base()
async def main(reader, writer):
   await base_script.initialize_program(reader, writer)
   exit_code = base_script.UNKNOWN
   monitor_message = "cabinet_alarm"
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
               # RETRIEVE PARAMETERS FROM RECEIVER CARDS
               # ---------------------------------------
               get_receiver_card_model(base_script.ser.port,no_of_receiver_cards,lan_value) #not necessary 
               get_receiver_card_firmware(base_script.ser.port,no_of_receiver_cards,lan_value) #not necessary 
               display_on = get_cabinet_kill_mode(base_script.ser.port,no_of_receiver_cards,lan_value) and display_on
               no_of_receiver_cards += 1
               receiver_card_found = get_receiver_connected(base_script.ser.port,no_of_receiver_cards,lan_value)
            except Exception as e:
               pass
   if(not display_on):
      message = "ONE OR MORE CABINETS OFF"
      exit_code = base_script.CRITICAL
      base_script.logger.error(f"{monitor_message}=1")
      base_script.logger.error(f"cabinet_message={message}")
   else:
      message = "All CABINETS OK"
      exit_code = base_script.GOOD
      base_script.logger.info(f"{monitor_message}=0")
      base_script.logger.info(f"cabinet_message={message}")

   base_script.ser.close() #closing 
   base_script.logger.info("Writing to JSON file")
   # -------------------------------------------------------------
   # TO DO
   # Include checks for brightness >0. This should be a WARNING.
   # -------------------------------------------------------------

   base_script.logger.info ("EXIT CODE: {}, {}".format(exit_code, message))
   
   # ----------------------------------------------------------------
   # TO DO
   # Consider including exit_code and output message into status.json     
   # ----------------------------------------------------------------  
   await base_script.monitoring_log_output(message,monitor_message, exit_code, reader, writer)
    
# ------------------------------------------------------------------------------------------------------------
# FUNCTION DEFINITIONS
def get_cabinet_kill_mode(port, receiver_index_value, lan_value):
#-------------------------------------------------------------------------
# CHECK KILL MODE (CABINET STATUS)
# This is essentially information about whether the display is ON or OFF
#-------------------------------------------------------------------------
   logger = logging.getLogger(base_script.LOGGER_NAME)
   logger.info("Getting cabinet kill mode (on/off)")
   kill_mode[7] = lan_value
   kill_mode[8] = receiver_index_value
   kill_mode_send = methods.checksum(kill_mode)
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in kill_mode_send))
   base_script.ser.write (kill_mode_send)
   time.sleep (base_script.sleep_time)
   inWaiting = base_script.ser.inWaiting()
   if inWaiting>0:
      response = base_script.ser.read(size=inWaiting)
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      rx_data_18 = rx_data[18]
      if base_script.check_response(rx_data):
         if (rx_data_18==0x00):
            logger.info ("Cabinet Operating Status (Kill mode): ON")
            kill="On"
            cabinet_on = True
         elif (rx_data_18==0xFF):
               logger.info ("Cabinet Operating Status (Kill mode): OFF")
               kill="Off"
               cabinet_on = False
         else:
            logger.info ("Cabinet Operating Status (Kill mode): UNKNOWN")
            kill="UNKNOWN"
            cabinet_on = False
      else:
         kill="N/A"
         cabinet_on = False
   else:
         logger.info ("No data available at the input buffer")
         kill="N/A"
         cabinet_on = False
   base_script.status[port]["receiverCard"][receiver_index_value]["kill"]=kill
   return cabinet_on
def get_receiver_connected(port, receiver_index_value, lan_value):
# ---------------------------------------------------------------------------------------
# CHECK CONNECTION TO RECEIVER CARD
# ---------------------------------------------------------------------------------------   
   base_script.logger = logging.getLogger(base_script.LOGGER_NAME)
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

 
def get_receiver_card_model(port,receiver_index_value, lan_value):
   logger = logging.getLogger(base_script.LOGGER_NAME)
   logger.info("Getting receiver card model")
   check_receiver_model[7] = lan_value
   check_receiver_model[8] = receiver_index_value
   check_receiver_model_send = methods.checksum (check_receiver_model)
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in check_receiver_model_send))
   base_script.ser.write (check_receiver_model_send)
   time.sleep (base_script.sleep_time)
   inWaiting = base_script.ser.inWaiting()
   if inWaiting>0:
      base_script.status[port]["receiverCard"][receiver_index_value]={}
      response = base_script.ser.read(size=inWaiting)
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      rx_data_18 = rx_data[18]
      rx_data_19 = rx_data[19]
      if base_script.check_response(rx_data):
         if (rx_data_19==0x45) and (rx_data_18==0x06):
            model = 'Nova A4s'
         elif (rx_data_19==0x45) and (rx_data_18==0x08):
            model = 'Nova A5s'
         elif (rx_data_19==0x45) and (rx_data_18==0x0A):
            model = 'Nova A7s'
         elif (rx_data_19==0x45) and (rx_data_18==0x09):
            model = 'Nova A8s'
         elif (rx_data_19==0x45) and (rx_data_18==0x0F):
            model = 'Nova MRV 366/ MRV 316'
         elif (rx_data_19==0x45) and (rx_data_18==0x10):
            model = 'Nova MRV 328'
         elif (rx_data_19==0x45) and (rx_data_18==0x0E):
            model = 'Nova MRV 308'
         elif (rx_data_19==0x46) and (rx_data_18==0x21):
            model = 'Nova A5s Plus'
         else:
            model =('{}'.format(hex(rx_data_19),hex(rx_data_19)))
      else:
          model = 'N/A'
      base_script.status[port]["receiverCard"][receiver_index_value]["receiverModel"]=model
      logger.info ('Receiver card model: {}'.format(model))
   else:
      logger.warning("No data available at the input buffer")
      receiver_card_found = False
   return

def get_receiver_card_firmware(port, receiver_index_value, lan_value):
# ---------------------------------------------------------------------------------------
# RECEIVER CARD FW VERSION
# ---------------------------------------------------------------------------------------  
   logger = logging.getLogger(base_script.LOGGER_NAME)
   logger.info("Getting receiver card firmware")
   check_receiver_fw [7] = lan_value
   check_receiver_fw [8] = receiver_index_value
   check_receiver_fw_send = methods.checksum (check_receiver_fw)
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in check_receiver_fw_send))
   base_script.ser.write (check_receiver_fw_send)
   time.sleep (base_script.sleep_time)
   inWaiting = base_script.ser.inWaiting()
   if inWaiting>0:
      response = base_script.ser.read(size=inWaiting)
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      rx_data_18 = rx_data[18]
      rx_data_19 = rx_data[19]
      rx_data_20 = rx_data[20]
      rx_data_21 = rx_data[21]
      if base_script.check_response(rx_data):
         FPGA=str(rx_data_18)+'.'+str(rx_data_19)+'.'+str(rx_data[20])+'.'+str("{:02x}".format(rx_data[21]))
      else:
         FPGA="N/A" 
   else:
         logger.warning("No data available at the input buffer")
         FPGA="N/A"
   base_script.status[port]["receiverCard"][receiver_index_value]["receiverFPGA"]=FPGA
   logger.info('Receiver Card FPGA Firmware version: {}'.format(FPGA))
# ------------------------------------------------------------------------------------------------------------
# PROGRAM ENTRY POINT - this won't be run only when imported from external module
# ------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    
   asyncio.run(base_script.communicate_with_server(main, "check_cabinet"))

