#!/usr/bin/env python3
import asyncio
from base_monitoring import *
base_script = base()
async def main(reader, writer):
   await base_script.initialize_program(reader, writer)
   exit_code = base_script.UNKNOWN
   monitor_message = "Modules"
   module_status_info = {}
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
               # ---------------------------------------
               # RETRIEVE PARAMETERS FROM RECEIVER CARDS
               # ---------------------------------------
               get_receiver_card_model(base_script.serial_port) #not necessary 
               get_receiver_card_firmware(base_script.serial_port) #not necessary 
               #################################################################################################
               number_of_modules, modules_ok = get_module_status(base_script.serial_port,  modules_ok, lan_value) #required
               #################################################################################################
               no_of_receiver_cards = no_of_receiver_cards+1
         ##############################################################################################
            except Exception as e:
               pass
            
   base_script.ser.close() #closing 
   i += 1

   #UPDATE INDEPENDANT CHECK DO NOT WIRTE TO STATUS.JSON FILE @
   # write_data(STATUS_FILE, status, LOGGER_NAME) # This could go to the end to 
   
   if (False in [value['module_status'] for value in module_status_info.values()]): #checking if a status does not return True
      msg = ""
      for receiver in module_status_info:
         module_status = module_status_info[receiver]['module_status']
         detected_modules = module_status_info[receiver]['detected_modules']
         if module_status is False:               
            expected_modules = base_script.config['modules']
            msg += f"ERROR IN ONE OR MORE MODULES - {expected_modules} EXPECTED, {detected_modules} FOUND, RECEIVER_NR {receiver} \n"         
      message = msg      
      exit_code = base_script.CRITICAL # Should this be CRITICAL? #MODULE_ERROR
   #TODO ADD BLOCK FAULT AS WARNING
   else:
      message = f"ALL MODULES OK"
      exit_code = base_script.GOOD

   await base_script.monitoring_log_output(message,monitor_message, exit_code, reader, writer)
   
   await icinga_output(message, exit_code, reader, writer)
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

#################################################################################################
def get_module_status(port,  modules_ok,receiver_index_value, lan_value):
#-----------------------------------------------------------------
   logger = logging.getLogger(base_script.LOGGER_NAME)
   logger.info("Getting module status")
   check_module_status [7] = lan_value
   check_module_status [8] = receiver_index_value
   data_groups = 4
   data_length = number_of_modules * (22+2*data_groups)
   print (data_length)
   first_byte = data_length & 0xFF00
   second_byte = data_length & 0x00FF
   print (first_byte, second_byte)
   check_module_status [16] = second_byte
   check_module_status [17] = first_byte
   element_length = 22 + (data_groups*2)
   print (element_length)
   # Here we must adjust length of data to be read (L) for NUMBER OF MODULES (N) and for DATA GROUPS PER MODULE (DG) according to the formula:
   # L = N * (22+2*DG)
   # Assumption for now is that N=4 (this value may be stored in config.json) and DG=1. Therefore:
   # L = 4 * (22+2*1) = 4 * (24) = 96 = 0x60 --> check_module_status [16] = 96
   check_module_status_send = methods.checksum(check_module_status)
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in check_module_status_send))
   base_script.ser.write(check_module_status_send)
   time.sleep(base_script.sleep_time)
   modules_ok = True
   # ------------------------------------------------------------------------------------------------
   # Read length of payload data received - payload will contain info for all N modules.
   # First byte (X0)represents LED module status (xFF=NORMAL; 0x00=PROBLEM)
   # (X1) to (X21) represents other data (such as power supply voltage, temperature and runtime of module?)
   # (X22) and (X23) represent cable detection --> These should both be 0 - any other value means an error
   # 
   # ------------------------------------------------------------------------------------------------
   if base_script.ser.inWaiting()>0:
         response = base_script.ser.read(size=base_script.ser.inWaiting())
         rx_data = list (response)
         logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
         #number_of_modules = int(rx_data[16]/4)
         #logger.info ("Total amount of modules: {}".format(number_of_modules))
         base_script.status[port]["receiverCard"][receiver_index_value]["module"]={}
         if base_script.check_response(rx_data):
            # Read X0-X23 bytes for each module expected
            # First, read the X0 byte for LED module status
            # Next, check flat cable data in bytes X22 and X23.
            # The Data Groups consist of 2 bytes (16 bits). Each bit is a Data Flag
            for j in range (int(number_of_modules)):
               base_script.status[port]["receiverCard"][receiver_index_value]["module"][j]={}
               element = rx_data[18+j*element_length:(18+j*element_length)+element_length]
               #print("MODULE STATUS: {:02X}",hex(element))
               logger.debug("MODULE STATUS: "+' '.join('{:02X}'.format(a) for a in element))
               #TODO assign the values to variables0xFF = OK etc.
               if (element[0]==0xFF):
                  module_sts= "OK"
                  modules_ok = modules_ok and True
               elif (element[0]==0x00):
                  module_sts = "Error or no module available"
                  modules_ok = modules_ok and False
               else:
                  module_sts = "Unkown module state"
                  modules_ok = modules_ok and True
                  
               if ((element[22] & 0xF) != 0) | ((element[24] & 0xF) != 0) | ((element[26] & 0xF) != 0)| ((element[28] & 0xF) != 0):
                  block_fault = "FAULT"
               else:
                  block_fault = "OK"                  
               logger.info ("Module {module_index}: STATUS:{write_result} (0x{write_hex:02X})   BLOCK FAULTS:{block}".format(module_index=j+1,write_result=module_sts,write_hex=element[0],block=block_fault))#.format(j+1).format(module_write).format(element[0]).format(module_read).format(element[1]))
               base_script.status[port]["receiverCard"][receiver_index_value]["module"][j]=module_sts
         else:
            modules_ok = modules_ok and False
            base_script.status[port]["receiverCard"][receiver_index_value]["module"]='N/A'
   else:
         logger.warning ("No data available at the input buffer")    
         number_of_modules = 0
         modules_ok = modules_ok and False
         module_status="N/A"    
         base_script.status[port]["receiverCard"][receiver_index_value]["module"]="N/A"
   return (number_of_modules,modules_ok)
#################################################################################################
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
   global no_of_receiver_cards
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
async def icinga_output(message, exit_status, reader, writer):
    """Outputs the result to Icinga and notifies the server."""
    print(message)
    try:
        writer.write(b"Done")
        await writer.drain()
        await reader.read(1024)
        writer.close()
        await writer.wait_closed()
        base_script.logger.info("Sent 'done' to server.")
    except Exception as e:
        base_script.logger.error(f"Error sending completion message: {e}")
    sys.exit(exit_status)
    
#----------------------------------------------------------------
if __name__ == "__main__":  
   asyncio.run(base_script.communicate_with_server(main, "check receiving card modules"))

      
