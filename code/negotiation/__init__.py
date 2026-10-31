"""Bargaining (build step 4): the hotel's counter_offer tool and Tuttie's negotiating subagents.

rules.py   the business side's limits and answers: pure functions, no LLM
hotel.py   POST /tools/counter_offer for every node (stateless, checks only signatures)
tuttie.py  Tuttie's side: one subagent per offer, all in parallel, within its private budget
"""
