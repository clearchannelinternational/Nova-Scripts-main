#!/usr/bin/env python3
import asyncio
from base_monitoring import *
def check_receiving_cards(base_script, total_receiver_cards, total_receiver_cards_found):
   if total_receiver_cards != total_receiver_cards_found:
      difference = total_receiver_cards - total_receiver_cards_found
      base_script.logger.error(f"receiving_cards_alarm=1")
      base_script.logger.error(f"receiving_cards_output='Total Faulty receiver cards: {difference}'")
   else:    
      base_script.logger.info(f"receiving_cards_alarm=0")
      base_script.logger.info(f"receiving_cards_output='Total Faulty receiver cards: 0'")