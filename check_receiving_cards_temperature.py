#!/usr/bin/env python3
import asyncio
from base_monitoring import *
base_script = base()
async def main(reader, writer):
   await base_script.initialize_program(reader, writer)
   exit_code = base_script.UNKNOWN
   monitor_message = "receiving_card_temperature"
   total_receiver_cards = base_script.config_panel["receiver_cards"]
   total_lan_ports = base_script.config_panel["lan_ports"]   #Validate device found on player
   total_receiver_cards_found = 0
   if (base_script.device_found == 0):
      message = "NO DEVICE - make sure a valid controller is connected, that the correct baudrate is defined in config.json and ensure the NOVA LCT is not running on the host system \nThis can also mean that you don't run the tool as administrator"
      exit_code = base_script.CRITICAL
      base_script.logger.info ("EXIT CODE: {}, {}".format(exit_code, message))
      await base_script.monitoring_log_output(message,monitor_message, exit_code, reader, writer)
   temperature_per_receiving_card = {}
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
               if not get_receiver_connected(no_of_receiver_cards,lan_value):
                  base_script.ser.close()
                  break
               temp_valid, temperature, voltage_valid, voltage, monitoring_card = get_receiver_temp_voltage(no_of_receiver_cards, lan_value)
                              
               if temp_valid and voltage_valid:
                  _status = 0;  
                  base_script.logger.info (f"Temperature: {temperature}")                
                  base_script.logger.info (f"Voltage: {voltage}")                
               elif temp_valid and not voltage_valid:
                  _status = 1
                  base_script.logger.info (f"Temperature: {temperature}")                
                  base_script.logger.error (f"Voltage: {voltage}")    
               elif not temp_valid and voltage_valid:
                  _status = 1
                  base_script.logger.error (f"Temperature: {temperature}")                
                  base_script.logger.info (f"Voltage: {voltage}")      
               else:
                  _status = 1
                  base_script.logger.error (f"Temperature: {temperature}")                
                  base_script.logger.error (f"Voltage: {voltage}")  
                                  
               temperature_per_receiving_card[f"{no_of_receiver_cards + 1}"] = {"temperature":temperature, "status":_status}                             
               no_of_receiver_cards += 1            
            except Exception as e:
               pass
   exit_code = base_script.GOOD
   message = "All receiving cards are at a normal level of temperature"
   for k in temperature_per_receiving_card.keys():
      if temperature_per_receiving_card[k]["status"] != 0:
         exit_code = base_script.WARNING
         message = "One or more receiving card's temperature are out of control"

         break      
   if exit_code != base_script.GOOD:
      base_script.logger.error(f"{monitor_message}=1")
      base_script.logger.error(f"receiving_cards_temperature_output={message}")
   else:
      base_script.logger.info(f"{monitor_message}=0")
      base_script.logger.info(f"receiving_cards_temperature_output={message}")
   base_script.ser.close() #closing 
   base_script.logger.info ("EXIT CODE: {}, {}".format(exit_code, message))
   await base_script.monitoring_log_output(message,monitor_message, exit_code, reader, writer)    
          
def get_receiver_connected(receiver_index_value, lan_value):
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
#Get receiving card gets one parameter (receiving_card) that represent the physical receiving card found per sender card
def get_receiver_temp_voltage(receiver_index_value, lan_value):
# ---------------------------------------------------------------------------------------
# CHECK TEMPERATURE, VOLTAGE & MONITORING
# Retrieve data for receiver cards
# Maximum resolution: 512 x 384 px @60Hz
# AC/DC: MEGMEET MCP260WL-4.5 / Output 4.5VDC 40A (4.2~5.0V)
# A5s PLUS
# Input voltage: 3.8 to 5.5 V
# Rated current: 0.6A
# Rated power consumption: 3.0 W
# Operating Temperature: -20C to 70C
#
# Device: Receiving Card 
# Base Address: 0a000000 H 
# Data Length: 100H
# ---------------------------------------------------------------------------------------
   global data
   global logger
   logger = logging.getLogger(base_script.LOGGER_NAME)
   logger.info("Getting receiver card monitoring, temperature and voltage")
   check_monitoring [7] = lan_value
   check_monitoring [8] = receiver_index_value
   check_monitoring_send = methods.checksum (check_monitoring)
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in check_monitoring_send))
   base_script.ser.write(check_monitoring_send)
   time.sleep(base_script.sleep_time)
   if base_script.ser.inWaiting()>0:
         response = base_script.ser.read(size=base_script.ser.inWaiting())
         rx_data = list (response)
         logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
         if base_script.check_response(rx_data):
            if ((rx_data[18] & 0x80))==0x80:
               if (rx_data[18]&0x1)==0:
                  sign = ""
               else:
                  sign = "-"
               logger.info("Temperature (valid): {}{:.1f}°C ({})".format(sign,(rx_data[19]&0xFE)*0.5,hex(rx_data[19])))
               temp_valid="Yes"
               temperature = sign+str((rx_data[19]&0xFE)*0.5)
               temperature = round(float(temperature), 2)
            else:
               logger.info ("Temperature data invalid")
               temp_valid="No"
               temperature="N/A"
            
            if ((rx_data[21]) & 0x80)==0x80:
               logger.info("Voltage (valid): {:.1f}V ({})".format(0.1*(rx_data[21]&0x7F),hex(rx_data[21])))
               voltage_valid="Yes"
               voltage=0.1*(rx_data[21]&0x7F)
               voltage = round(float(voltage), 2)#
            else:
               logger.info ("Voltage data invalid")
               voltage_valid="No"
               voltage="N/A"

            if (rx_data[50]==0xFF):
               logger.info ("Monitoring card available ({})".format(hex(rx_data[50])))
               monitoring_card="Yes"
            else:
               logger.info ("Monitoring card unavailable ({})".format(hex(rx_data[50])))
               monitoring_card="No"
         else:
            temp_valid="N/A"
            temperature="N/A"
            voltage_valid="N/A"
            voltage="N/A"
            monitoring_card="N/A"          
   else:
         logger.info ("No data available at the input buffer")
         temp_valid="N/A"
         temperature="N/A"
         voltage_valid="N/A"
         voltage="N/A"
         monitoring_card="N/A"
   return temp_valid, temperature, voltage_valid, voltage, monitoring_card

# ------------------------------------------------------------------------------------------------------------
# PROGRAM ENTRY POINT - this won't be run only when imported from external module
# ------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
   asyncio.run(base_script.communicate_with_server(main, "temperature per receiving cards"))
