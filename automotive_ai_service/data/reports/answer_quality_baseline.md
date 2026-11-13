# Answer quality: baseline

4 of 100 cases passed (114 turns).
Answer length: mean 231.0 words, median 199, max 657.

| Metric | Passed | Rate |
|---|---|---|
| accuracy | 42/85 | 0.494 |
| conciseness | 19/104 | 0.183 |
| consistency | 5/7 | 0.714 |
| context_awareness | 0/9 | 0.0 |
| expected_kind | 92/112 | 0.821 |
| hallucination | 15/16 | 0.938 |
| no_leakage | 26/114 | 0.228 |
| relevance | 43/95 | 0.453 |
| retrieval | 45/94 | 0.479 |
| safety | 17/20 | 0.85 |

## Failed cases

- **tire_flat** "What should I do if my tire is flat?" -> answer/tire_puncture (199 words): failed relevance, conciseness, no_leakage
- **tire_pressure** "How often should I check my tire pressure?" -> answer/tire_pressure_tread (147 words): failed accuracy, conciseness, no_leakage
- **tire_pressure_number** "What tire pressure should my Toyota Vios have?" -> answer/tire_pressure_tread (147 words): failed conciseness, no_leakage
- **tire_blowout** "My tire blew out on the highway" -> answer/high_speed_vibration (260 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **tire_sidewall** "There's a bulge on the sidewall of my tire" -> answer/tire_pressure_tread (171 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **tire_uneven** "Why are my tires wearing on the inside edge?" -> answer/tire_pressure_tread (185 words): failed retrieval, relevance, conciseness, no_leakage
- **tire_rotation** "What is tire rotation?" -> answer/tire_pressure_tread (147 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **wheel_balancing** "What is wheel balancing?" -> answer/brake_vibration (272 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **overheat_follow_up** "Why is my car overheating?" -> answer/engine_overheating (645 words): failed conciseness, no_leakage
- **overheat_follow_up** "What if the coolant is full?" -> answer/engine_overheating (645 words): failed relevance, conciseness, context_awareness, no_leakage
- **overheat_safe** "My temperature gauge is going up" -> answer/engine_overheating (645 words): failed conciseness, no_leakage
- **overheat_safe** "Is it safe to keep driving?" -> answer/None (425 words): failed retrieval, relevance, conciseness, context_awareness, no_leakage
- **misfire** "My engine is misfiring" -> answer/engine_misfire (141 words): failed accuracy, conciseness, no_leakage
- **check_engine_flashing** "My check engine light is flashing" -> answer/check_engine_flashing (217 words): failed conciseness, no_leakage
- **oil_light** "The red oil pressure light came on while driving" -> answer/oil_pressure_leak (151 words): failed conciseness, no_leakage
- **oil_check** "How do I check my engine oil?" -> answer/None (318 words): failed retrieval, relevance, conciseness, no_leakage
- **oil_change** "How often should I change engine oil?" -> answer/oil_change_schedule (166 words): failed conciseness, no_leakage
- **engine_knock** "My engine is making a knocking noise" -> answer/None (69 words): failed retrieval, relevance, no_leakage
- **cranks_no_start** "The engine cranks but won't start" -> answer/fuel_ignition_air (139 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **blue_smoke** "Blue smoke from my exhaust" -> answer/exhaust_blue_smoke (199 words): failed conciseness, no_leakage
- **white_smoke** "white smoke from exhaust" -> answer/exhaust_smoke_color (317 words): failed conciseness, no_leakage
- **timing_belt** "What does a timing belt do?" -> answer/timing_engine_wear (126 words): failed accuracy, conciseness, no_leakage
- **battery_click** "Car won't start, just clicking" -> answer/battery_charging_starting (136 words): failed conciseness, no_leakage
- **alternator_role** "What does an alternator do?" -> answer/battery_charging_starting (56 words): failed no_leakage
- **battery_light** "The battery light came on while driving" -> answer/battery_charging_light (228 words): failed conciseness, no_leakage
- **battery_dies_overnight** "My battery dies overnight" -> answer/battery_charging_starting (136 words): failed accuracy, conciseness, no_leakage
- **blown_fuse** "My radio stopped working, could it be a blown fuse?" -> answer/None (89 words): failed accuracy, retrieval, relevance
- **burning_plastic** "I smell burning plastic from the dashboard" -> abstain/None (56 words): failed expected_kind, accuracy, retrieval, relevance, safety
- **battery_care** "How do I take care of my car battery?" -> answer/battery_charging_light (235 words): failed retrieval, relevance, conciseness, no_leakage
- **spongy_brakes** "My brakes feel spongy" -> answer/brake_wear (201 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **brake_failure** "My brakes are not working while driving" -> answer/None (241 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **brake_squeal** "my brakes are squeaking when I stop" -> answer/brake_noise (328 words): failed conciseness, no_leakage
- **brake_grinding** "grinding noise when I brake" -> answer/brake_grinding (230 words): failed conciseness, no_leakage
- **abs_light** "What does the ABS light mean?" -> answer/brake_warning_abs (139 words): failed accuracy, conciseness, no_leakage
- **brake_fluid** "When should brake fluid be changed?" -> answer/brake_warning_abs (179 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **brake_vibration** "Car shakes when braking." -> answer/brake_vibration (230 words): failed conciseness, no_leakage
- **brake_pads_role** "What do brake pads do?" -> answer/brake_wear (147 words): failed conciseness, no_leakage
- **trans_slip** "Transmission slipping" -> answer/transmission_slip (143 words): failed conciseness, no_leakage
- **trans_fluid** "How do I check transmission fluid?" -> answer/transmission_slip (155 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **trans_fluid_capacity** "How many liters of transmission fluid does my car need?" -> answer/transmission_slip (148 words): failed conciseness, no_leakage
- **grinding_gears** "It's hard to shift gears in my manual car" -> needs_data/None (0 words): failed expected_kind, accuracy, retrieval, relevance
- **trans_noise** "My transmission is whining" -> answer/transmission_slip (143 words): failed retrieval, relevance, conciseness, no_leakage
- **heavy_steering** "My steering is heavy" -> answer/steering_heavy (233 words): failed conciseness, no_leakage
- **steering_failure** "I lost steering while driving" -> answer/None (451 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **steering_lock** "My steering wheel is locked and the key won't turn" -> answer/steering_heavy (233 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **worn_shocks** "My car keeps bouncing after bumps" -> abstain/None (56 words): failed expected_kind, accuracy, retrieval, relevance
- **alignment** "My steering wheel is not straight when driving straight" -> answer/vehicle_pulling (279 words): failed retrieval, relevance, conciseness, no_leakage
- **pulling** "Car pulls to the left." -> answer/vehicle_pulling (242 words): failed conciseness, no_leakage
- **high_speed_shake** "My steering wheel shakes at high speed" -> answer/high_speed_vibration (241 words): failed conciseness, no_leakage
- **cv_click** "Clicking noise when turning" -> answer/cv_joint_clicking (220 words): failed conciseness, no_leakage
- **severe_shake** "My car suddenly started shaking violently" -> answer/high_speed_vibration (264 words): failed retrieval, relevance, conciseness, no_leakage
- **power_steering_whine** "Whining noise when turning the steering wheel" -> answer/steering_heavy (257 words): failed retrieval, relevance, conciseness, no_leakage
- **fuel_smell** "I smell gasoline near the car" -> needs_data/None (0 words): failed expected_kind, accuracy, retrieval, relevance, safety
- **engine_smoke** "There is smoke coming from under the hood" -> answer/exhaust_blue_smoke (211 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **ev_battery** "Can I open the high-voltage battery pack?" -> answer/hybrid_ev_high_voltage_safety (251 words): failed accuracy, conciseness, no_leakage
- **coolant_change** "What coolant should I use?" -> answer/engine_overheating (645 words): failed retrieval, relevance, conciseness, no_leakage
- **service_schedule** "When should I service my car?" -> answer/maintenance_schedule_overdue (143 words): failed conciseness, no_leakage
- **air_filter** "When do I replace the air filter?" -> answer/fuel_ignition_air (216 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **ac_warm** "My aircon is blowing warm air" -> answer/hvac_air_conditioning (253 words): failed conciseness, no_leakage
- **dtc_p0420** "What is P0420?" -> dtc/None (230 words): failed relevance, conciseness
- **dtc_p0300** "What does code P0300 mean?" -> dtc/None (287 words): failed conciseness
- **dtc_p0171** "P0171" -> dtc/None (355 words): failed conciseness
- **dtc_follow_up** "What is P0300?" -> dtc/None (287 words): failed conciseness
- **dtc_follow_up** "What causes it?" -> answer/engine_overheating (657 words): failed expected_kind, accuracy, conciseness, no_leakage
- **dtc_manufacturer** "What is P1456?" -> dtc/None (42 words): failed no_leakage
- **dtc_types** "What is the difference between P0 and P1 codes?" -> answer/symptom_vs_fault (145 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **warning_light_general** "What does the check engine light mean?" -> answer/dashboard_warning_obd (147 words): failed conciseness, no_leakage
- **rental_inspection** "What should I check before renting a car?" -> needs_data/None (0 words): failed expected_kind, accuracy, retrieval, relevance
- **rental_damage** "I scratched the rental car, what should I do?" -> needs_data/None (0 words): failed expected_kind, accuracy, retrieval, relevance
- **rental_fault** "There's a warning light on my rental car" -> answer/dashboard_warning_obd (147 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **vague_noise** "My car makes a noise" -> answer/brake_noise (374 words): failed expected_kind, no_leakage
- **vague_problem** "Something is wrong with my car" -> answer/None (127 words): failed expected_kind, no_leakage
- **vague_smell** "My car smells weird" -> answer/None (48 words): failed expected_kind, accuracy
- **vague_light** "A light came on on my dashboard" -> answer/dashboard_warning_obd (147 words): failed expected_kind, no_leakage
- **vague_then_specific** "My car makes a strange noise" -> answer/brake_noise (374 words): failed expected_kind, no_leakage
- **vague_then_specific** "It squeals when I brake" -> answer/brake_noise (328 words): failed conciseness, no_leakage
- **topic_change** "Why is my car overheating?" -> answer/engine_overheating (645 words): failed conciseness, no_leakage
- **topic_change** "What about a flat tire?" -> answer/tire_puncture (199 words): failed conciseness, no_leakage
- **follow_up_fix** "My steering is heavy" -> answer/steering_heavy (233 words): failed conciseness, no_leakage
- **follow_up_fix** "Is it safe to drive?" -> answer/None (398 words): failed retrieval, relevance, conciseness, context_awareness, no_leakage
- **follow_up_cost** "Transmission slipping" -> answer/transmission_slip (143 words): failed conciseness, no_leakage
- **follow_up_cost** "How much will it cost to fix?" -> answer/None (22 words): failed accuracy, retrieval, relevance
- **follow_up_checked** "Car won't start, just clicking" -> answer/battery_charging_starting (136 words): failed conciseness, no_leakage
- **follow_up_checked** "The battery is new" -> abstain/None (56 words): failed expected_kind, accuracy, retrieval, relevance, context_awareness
- **follow_up_more** "My engine is misfiring" -> answer/engine_misfire (141 words): failed conciseness, no_leakage
- **follow_up_more** "What else could it be?" -> abstain/None (56 words): failed expected_kind, retrieval, relevance, context_awareness
- **unrelated_sports** "Who won the NBA finals?" -> answer/motorcycle_chain_drive (214 words): failed expected_kind, hallucination, no_leakage
- **torque_value** "What is the torque for the wheel nuts on my car?" -> answer/None (241 words): failed conciseness, no_leakage
- **oil_capacity** "How many liters of oil does my engine take?" -> answer/oil_pressure_leak (151 words): failed conciseness, no_leakage
- **floaty_ride** "the car feels like it's floating over bumps" -> abstain/None (56 words): failed expected_kind, accuracy, retrieval, relevance
- **orange_engine_symbol** "what's that orange engine symbol on my dash" -> abstain/None (56 words): failed expected_kind, retrieval, relevance
- **dim_lights_died** "my headlights are dim and the car died" -> answer/None (58 words): failed retrieval, relevance, no_leakage
- **idle_vibration** "car vibrates when I idle at a red light" -> answer/engine_misfire (177 words): failed conciseness, no_leakage
- **ac_musty** "the AC smells musty" -> answer/hvac_air_conditioning (253 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **water_coolant** "can I use water instead of coolant" -> answer/engine_overheating (643 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **jerky_shift** "my car jerks when shifting from 2nd to 3rd" -> answer/transmission_slip (143 words): failed conciseness, no_leakage
- **hum_with_speed** "I hear a humming noise that gets louder with speed" -> answer/cv_joint_clicking (285 words): failed retrieval, relevance, conciseness, no_leakage
- **ran_over_nail** "i ran over a nail" -> abstain/None (56 words): failed expected_kind, accuracy, retrieval, relevance
- **catalytic_role** "what does a catalytic converter do" -> answer/exhaust_emissions_dpf (91 words): failed accuracy, conciseness, no_leakage
- **hard_brake_pedal** "my brake pedal is hard to press" -> answer/brake_wear (147 words): failed accuracy, retrieval, relevance, conciseness, no_leakage
- **temp_light_follow_ups** "engine temperature warning light" -> answer/dashboard_warning_obd (147 words): failed retrieval, relevance, conciseness, safety, no_leakage
- **temp_light_follow_ups** "what should i do now?" -> abstain/None (56 words): failed expected_kind, accuracy, retrieval, relevance, context_awareness
- **temp_light_follow_ups** "how much will that cost" -> clarify/None (30 words): failed expected_kind, accuracy, retrieval, relevance
- **replaced_plugs** "My engine is misfiring" -> answer/engine_misfire (141 words): failed conciseness, no_leakage
- **replaced_plugs** "I already replaced the spark plugs" -> answer/fuel_ignition_air (139 words): failed retrieval, relevance, conciseness, context_awareness, no_leakage
- **lights_work_fine** "my car won't start" -> answer/battery_charging_starting (136 words): failed conciseness, no_leakage
- **lights_work_fine** "the lights work fine though" -> answer/None (141 words): failed accuracy, retrieval, relevance, conciseness, context_awareness, no_leakage
- **dtc_serious** "P0128" -> dtc/None (252 words): failed conciseness
- **dtc_serious** "is it serious?" -> dtc/None (252 words): failed accuracy, conciseness, context_awareness
- **rental_check_engine** "my rental car has a check engine light, what do I do" -> answer/dashboard_warning_obd (147 words): failed accuracy, conciseness, no_leakage
