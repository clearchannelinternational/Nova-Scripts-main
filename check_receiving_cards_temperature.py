#!/usr/bin/env python3
import asyncio
from base_monitoring import *
base_script = base()
async def check_receiving_cards_temperature(port, no_of_receiver_cards, lan_value):
   monitor_message = "receiving_card_temperature"
   temperature_per_receiving_card =[]
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
   #default exit code is GOOD and message is indicating that all receiving cards are at a normal level of temperature and voltage
   exit_code = base_script.GOOD
   message = "All receiving cards are at a normal level of temperature/voltage"
   # Check if the status is not 0, which means that at least one of the receiving cards has an issue with temperature or voltage and set the exit code to CRITICAL and message accordingly
   if _status ==1:
      exit_code = base_script.CRITICAL
      message = "One or more receiving card's temperature/voltage are out of control"
      
   if exit_code != base_script.GOOD:
      base_script.logger.error(f"{monitor_message}=1")
      base_script.logger.error(f"receiving_cards_temperature_output={message}")
   else:
      base_script.logger.info(f"{monitor_message}=0")
      base_script.logger.info(f"receiving_cards_temperature_output={message}")

   base_script.logger.info ("EXIT CODE: {}, {}".format(exit_code, message))
          
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
