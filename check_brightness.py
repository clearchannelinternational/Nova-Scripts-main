#!/usr/bin/env python3
from base_monitoring import *
<<<<<<< HEAD
async def check_brightness(base_script):
   base_script = base_script
   exit_code = base_script.UNKNOWN
   monitor_message = "brightness"
   output = []        
   try: 
=======
base_script = base()
async def check_brightness(reader, writer):

   exit_code = base_script.UNKNOWN
   monitor_message = "check_brightness"
   output = []        
   try: 
      if base_script.ser.isOpen() == False:
         base_script.ser.open()
>>>>>>> 94990be71ff2d73a04472b6c6845ed7a7d6d72d7
      base_script.ser.flushInput() #flush input buffer, discarding all its contents
      base_script.ser.flushOutput() #flush output buffer, aborting current output and discard all that is in buffer
      base_script.logger.info("Opened device on port: " + base_script.ser.name) # remove at production
      # Retrieve parameters from sender cards
<<<<<<< HEAD
      brightness_value, exit_code = get_display_brightness(base_script) 
=======
      brightness_value, exit_code = get_display_brightness(base_script.ser.port) 
      base_script.ser.close() #closing 
>>>>>>> 94990be71ff2d73a04472b6c6845ed7a7d6d72d7
      base_script.logger.info("Writing to JSON file")
      base_script.logger.info("{} closed".format(base_script.ser.is_open)) # remove at production?

      if exit_code == base_script.GOOD and brightness_value > 0: 
         message = "Brightness OK"
<<<<<<< HEAD
         base_script.logger.info(f"{monitor_message}_alarm=0")
         base_script.logger.info(f"{monitor_message}_output={message}")
=======
         base_script.logger.info(f"{monitor_message}=0")
         base_script.logger.info(f"brightness_message={message}")
>>>>>>> 94990be71ff2d73a04472b6c6845ed7a7d6d72d7
         base_script.logger.info(f"brightness_value={brightness_value}%")
         
      else:
         message = "Brightness Not OK" 
<<<<<<< HEAD
         base_script.logger.critical(f"{monitor_message}=1")
         base_script.logger.critical(f"{monitor_message}_output={message}")
=======
         base_script.logger.critical(f"{monitor_message}=0")
         base_script.logger.critical(f"brightness_message={message}")
>>>>>>> 94990be71ff2d73a04472b6c6845ed7a7d6d72d7
         base_script.logger.critical(f"brightness_value={brightness_value}%")
   except Exception as e:
      base_script.logger.error(f"{e}")
      base_script.logger.error(f"Problem occured")      


   base_script.logger.info ("EXIT CODE: {}, {}".format(exit_code, message))

    
#################################################################################################

def get_display_brightness(base_script):
# ---------------------------------------------------------------------------------------
# SCREEN BRIGHTNESS SETTINGS
# This needs to be on a per receiver card basis or global?
# ---------------------------------------------------------------------------------------
   port = base_script.ser.port
   base_script.logger.info("Getting current screen brightness...[TO CHECK]")
   display_brightness_send = methods.checksum(display_brightness)
   base_script.logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in display_brightness_send))
   base_script.ser.write (display_brightness_send)
   time.sleep (base_script.sleep_time)
   if base_script.ser.inWaiting()>0:
      response = base_script.ser.read(size=base_script.ser.inWaiting())
      rx_data = list(response)
      base_script.logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if base_script.check_response(rx_data):
         brightness = rx_data[18]
         brightness_pc = round(100*brightness/255)
         base_script.logger.info("Brightness Level: "+ str(brightness))
         base_script.logger.info("Global Brightness: {}% ".format(brightness_pc))
         base_script.status[port]["brightnessLevelPC"] = brightness_pc
         base_script.status[port]["brightnessLevel"] = brightness
         exit_code = base_script.GOOD
      else:
         base_script.status[port]["brightnessLevelPC"] = "N/A"
         base_script.status[port]["brightnessLevel"] = "N/A"
         exit_code = base_script.CRITICAL
   else:
         base_script.logger.warning("No data available at the input buffer")
         base_script.status[port]["brightnessLevelPC"] = "N/A"
         base_script.status[port]["brightnessLevel"] = "N/A"
         exit_code = base_script.UNKNOWN
   return base_script.status[port]["brightnessLevelPC"], exit_code
