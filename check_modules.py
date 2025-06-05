#!/usr/bin/env python3
import asyncio
from base_monitoring import *
async def check_modules(base_script, no_of_receiver_cards, lan_value):
   monitor_message = "module"
   module_status_info = {}
   expected_modules = base_script.config['modules']
   base_script.status[base_script.ser.port]["receiverCard"]={}
   # ---------------------------------------
   # RETRIEVE PARAMETERS FROM RECEIVER CARDS
   # ---------------------------------------
   get_receiver_card_model(base_script, no_of_receiver_cards, lan_value) #not necessary 
   get_receiver_card_firmware(base_script, no_of_receiver_cards, lan_value) #not necessary 

   number_of_modules, modules_ok = get_module_status(base_script, base_script.modules_ok,no_of_receiver_cards,lan_value) #required
   #TODO: log each receiving card module information !
   if modules_ok:
      base_script.logger.info(f"Receiver {no_of_receiver_cards} MODULES FOUND: {number_of_modules} EXPECTED: {expected_modules}")
   else:
      base_script.logger.error(f"Receiver {no_of_receiver_cards} MODULES FOUND: {number_of_modules} EXPECTED: {expected_modules}")
 
   if (False in [value['module_status'] for value in module_status_info.values()]): #checking if a status does not return True
      for receiver in module_status_info:
         module_status = module_status_info[receiver]['module_status']
         detected_modules = module_status_info[receiver]['detected_modules']
         if module_status is False:                           
            message = f"ERROR IN ONE OR MORE MODULES - {expected_modules} EXPECTED, {detected_modules} FOUND, RECEIVER_NR {receiver}, COM {base_script.ser.port} LAN {lan_value} \n"             
      exit_code = base_script.CRITICAL # Should this be CRITICAL? #MODULE_ERROR
      base_script.logger.error(f"{monitor_message}_alarm=1")
      base_script.logger.error(f"{monitor_message}_output={message}")
   #TODO ADD BLOCK FAULT AS WARNING
   else:
      message = f"ALL MODULES OK"
      exit_code = base_script.GOOD
      base_script.logger.info(f"{monitor_message}_alarm=0")
      base_script.logger.info(f"{monitor_message}_output={message}")
#################################################################################################
def get_module_status(base_script,  modules_ok,receiver_index_value, lan_value):
#-----------------------------------------------------------------
   port = base_script.ser.port
   logger = logging.getLogger(base_script._logger_name)
   logger.info("Getting module status")
   check_module_status [7] = lan_value
   check_module_status [8] = receiver_index_value
   data_groups = 4
   data_length = base_script.number_of_modules * (22+2*data_groups)
   first_byte = data_length & 0xFF00
   second_byte = data_length & 0x00FF
   check_module_status [16] = second_byte
   check_module_status [17] = first_byte
   element_length = 22 + (data_groups*2)
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
            for j in range (int(base_script.number_of_modules)):
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
         base_script.number_of_modules = 0
         modules_ok = modules_ok and False
         module_status="N/A"    
         base_script.status[port]["receiverCard"][receiver_index_value]["module"]="N/A"
   return (base_script.number_of_modules,modules_ok)
#################################################################################################
def get_receiver_card_model(base_script,receiver_index_value, lan_value):
   port = base_script.ser.port
   logger = logging.getLogger(base_script._logger_name)
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

def get_receiver_card_firmware(base_script, receiver_index_value, lan_value):
# ---------------------------------------------------------------------------------------
# RECEIVER CARD FW VERSION
# ---------------------------------------------------------------------------------------
   port = base_script.ser.port
   global no_of_receiver_cards
   logger = logging.getLogger(base_script._logger_name)
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
    