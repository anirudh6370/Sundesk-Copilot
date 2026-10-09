# Aravalli Solar Works — Inverter and Monitoring Troubleshooting Runbook

This runbook is for Service Desk agents and Field Service engineers. Error codes starting with "AS-" are Aravalli codes shown in the Sun app and on the HelioBox gateway.

## Before Anything Else

Ask the customer whether there is a burning smell, smoke, sparks, a hot or discoloured box, or water inside any electrical enclosure. If yes, treat it as P1: tell the customer to follow the emergency shutdown card, keep away from the equipment and call the emergency line. Do not ask the customer to open any enclosure.

## Emergency Shutdown Sequence

1. Switch off the AC isolator next to the inverter.
2. Switch off the solar MCB in the main distribution board.
3. Turn the DC isolator on the inverter to OFF.
4. Do not touch the panels or DC cables. Panels produce voltage whenever there is daylight.

To restart, reverse the order: DC isolator ON, then solar MCB, then AC isolator. The inverter takes up to 5 minutes to reconnect to the grid.

## Error Code Reference

Each entry below explains what the code shown in the Sun app or on the inverter display means, what to check first, and the ticket priority.

### Grid codes

- Error code AS-101 means the grid voltage is out of range. First action: wait 15 minutes; it usually clears when the grid stabilises. Priority P3.
- Error code AS-102 means the grid frequency is out of range. First action: wait 15 minutes; log it if it repeats three times in a week. Priority P3.
- Error code AS-110 means no grid is detected. First action: check for a power cut and check the solar MCB. Priority P2.

### DC side and earth fault codes

- Error code AS-201 means low insulation resistance on the DC side. First action: do not restart; book a field visit. Priority P2.
- Error code AS-205 means the DC string voltage is too low. First action: check for shading or heavy soiling; book a visit if it persists for two days. Priority P3.
- Error code AS-210 means an earth fault is detected. First action: emergency shutdown, then book an urgent field visit. Priority P1.

### Inverter codes

- Error code AS-301 means the inverter is over temperature (overheating). First action: check that the inverter has ventilation and is not in direct sunlight. Priority P3.
- Error code AS-305 means an internal inverter fault. First action: restart once; if the code returns, raise a warranty claim. Priority P2.

### Monitoring and battery codes

- Error code AS-401 means the HelioBox gateway is offline. First action: check the Wi-Fi router and the gateway power. Priority P3.
- Error code AS-405 means a HelioBox data gap. First action: none, unless the gap exceeds 24 hours. Priority P4.
- Error code AS-501 means battery communication is lost (SunVault). First action: restart the battery unit; book a visit if it does not clear. Priority P2.

## System Producing No Power

1. Confirm it is daytime with reasonable sunlight. Inverters sleep at night.
2. Ask whether there is a power cut. Grid-tied systems stop producing during a power cut by design. This is the anti-islanding safety feature and is not a fault.
3. Ask the customer to read the code on the inverter display or in the Sun app.
4. Check that the solar MCB in the distribution board has not tripped.
5. If the MCB has tripped, it may be reset once. If it trips again, stop and book a field visit.
6. If there is no code and the display is blank in daylight, raise a P2 ticket.

## Generation Lower Than Expected

- Compare with the same month last year, not with the previous month. Winter and monsoon months are naturally lower.
- A drop of up to 15 percent during monsoon months is normal.
- Check when the panels were last cleaned. Dust can reduce generation by 5 to 20 percent.
- Look for new shading: a new building, a water tank, a grown tree or a dish antenna.
- If one string is much lower than the other in the Sun app, raise a P3 ticket for string inspection.

## HelioBox Offline (AS-401)

1. Check the gateway light. Steady green means online, blinking amber means no Wi-Fi, no light means no power.
2. If the customer changed the Wi-Fi name or password, re-pair the gateway: hold the pairing button for 5 seconds, then use "Add Gateway" in the Sun app.
3. HelioBox supports 2.4 GHz Wi-Fi only. A 5 GHz-only router will not work.
4. The system keeps generating power while the gateway is offline. Only the monitoring data is missing.

## When to Book a Field Visit

Book a visit when a code returns after one restart, when the same code appears three times within seven days, when there is any DC-side or earth fault code, or when the customer is not comfortable carrying out a check.
