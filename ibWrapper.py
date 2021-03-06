# -*- coding: utf-8 -*-
from time import sleep
from ib.ext.Contract import Contract
from ib.ext.Order import Order
from ib.opt import ibConnection
from logging.handlers import TimedRotatingFileHandler

import logging
import os
import re
import json


class IBWrapper:
    nextOrderId = 0
    account_id = None

    # --- creating log file handler --- #
    if not os.path.isdir('logs'):
        os.makedirs('logs')
    logger = logging.getLogger("IBWrapper")
    logger.setLevel(logging.INFO)

    # create file, formatter and add it to the handlers
    fh = TimedRotatingFileHandler('logs/IBWrapper.log', when='d',
                                  interval=1, backupCount=10)
    fh.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(process)d - %(name)s '
                                  '(%(levelname)s) : %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    # --- Done creating log file handler --- #

    def __init__(self, ip, port, client_id, sig_multiplier=1, uilogger=None):

        self.con_str = ''.join([ip, ":", str(port)])
        self.con = ibConnection(ip, port, client_id)
        self.sig_multiplier = sig_multiplier
        self.uilogger = uilogger

        # Assign corresponding handling function to message types
        self.con.register(self.my_account_handler, 'UpdateAccountValue')
        self.con.register(self.error_handler, 'Error')
        self.con.register(self.next_valid_id_handler, 'NextValidId')
        self.con.register(self.managed_account_handler, 'ManagedAccounts')
        # self.con.register(self.my_tick_handler, message.tickSize, message.tickPrice)

        # Assign rest of server reply messages to the
        # reply_handler function
        # self.con.registerAll(self.reply_handler)

        # reading ib's symbol mapping
        with open('conf/ibsymbols.json', 'r') as cf:
            self.symbol_map = json.loads(cf.read())

    def connect(self):
        if self.con.connect():
            self.logger.info('connected to IB on ' + self.con_str)
            # give it a second to get data
            sleep(1)
        # raise ValueError('Fail to connect to IB!')

    def my_account_handler(self, msg):
        self.logger.info(msg)

    def managed_account_handler(self, msg):
        """Handles the capturing of account id"""
        regex = re.search(r'accountsList=(\w+)', str(msg))
        if regex:
            self.account_id = regex.group(1)
            self.logger.info("IB account: %s" % self.account_id)
        else:
            raise ValueError("No account id found in msg: " + msg)

    def my_tick_handler(self, msg):
        self.logger.info(msg)

    def next_valid_id_handler(self, msg):
        """Handles the capturing of next valid order id"""
        regex = re.search(r'orderId=(\d+)', str(msg))
        if regex:
            self.nextOrderId = int(regex.group(1))
            self.logger.info("next valid id: %d" % self.nextOrderId)
        else:
            raise ValueError("No next valid id found in msg: " + msg)

    def error_handler(self, msg):
        """Handles the capturing of error messages"""
        regex = re.search(r'<.*errorCode=(.*),\serrorMsg=(.*)>', str(msg))
        if regex:
            err_code = regex.group(1)
            err_msg = regex.group(2)
            self.logger.error("IB Error [code: %s, message: %s]" % (err_code, err_msg))
            if err_code == 'None' and err_msg.startswith('unpack requires a string'):
                self.log_all("IB account " + self.account_id + " was shutdown!", 'error')
        else:
            self.logger.error("IB Error: %s" % msg)

    def reply_handler(self, msg):
        """Handles of server replies"""
        self.logger.info("Server Response: %s, %s" % (msg.typeName, msg))

    def create_contract(self, symbol, sec_type, exch='SMART', prim_exch='SMART', curr='USD'):
        """
        Create a Contract object defining what will
        be purchased, at which exchange and in which currency.

        symbol - The ticker symbol for the contract
        sec_type - The security type for the contract ('STK' is 'stock')
        exch - The exchange to carry out the contract on
        prim_exch - The primary exchange to carry out the contract on
        curr - The currency in which to purchase the contract
        """
        sec_type = sec_type.lower()
        symbol = symbol.lower()

        # check the symbol map to see if any attributes were defined for this symbol's order
        # e.g. "GLD" has primary exchange defined to disambiguate from "GLD" of foreign exchanges.
        if sec_type in self.symbol_map:
            if symbol in self.symbol_map[sec_type]:
                if 'prim_exch' in self.symbol_map[sec_type][symbol]:
                    prim_exch = str(self.symbol_map[sec_type][symbol]['prim_exch'])

        contract = Contract()
        contract.m_symbol = symbol
        contract.m_secType = sec_type
        contract.m_exchange = exch
        contract.m_primaryExch = prim_exch
        contract.m_currency = curr

        return contract

    def create_order(self, order_type, quantity, action):
        """Create an Order object (Market/Limit) to go long/short.

        order_type - 'MKT', 'LMT' for Market or Limit orders
        quantity - Integral number of assets to order
        action - 'BUY' or 'SELL'
        """
        order = Order()
        order.m_orderType = order_type
        order.m_totalQuantity = quantity
        order.m_action = action
        return order

    def placeOrder(self, order_id, contract, order):
        return self.con.placeOrder(order_id, contract, order)

    def disconnect(self):
        self.log_all('Disconnecting IB account %s @ %s' % (self.account_id, self.con_str))
        self.con.disconnect()

    def reqQuote(self, contract):
        self.con.reqMktData(1, contract, '', False)

    def log_all(self, message, level='info'):
        if level == 'info':
            self.logger.info(message)
            if self.uilogger:
                self.uilogger.info(message)
        else:
            self.logger.error(message)
            if self.uilogger:
                self.uilogger.error(message)


if __name__ == '__main__':
    # print 'acct update...'
    # con.reqAccountUpdates(1, '')
    # sleep(1)

    ib = IBWrapper('localhost', 7496, 1)
    ib.connect()

    # Create an order ID which is 'global' for this session. This
    # will need incrementing once new orders are submitted.
    order_id = ib.nextOrderId

    print ">>> order id is", order_id

    # Create a contract 
    contract = ib.create_contract('gld', 'stk')

    # create order
    order = ib.create_order('mkt', 200, 'sell')

    # Use the connection to the send the order to IB
    ret = ib.placeOrder(order_id, contract, order)

    print "placeOrder returned: ", ret
    sleep(1)
    # print 'disconnected', con.disconnect()
    # sleep(3)
    # print 'reconnected', con.reconnect()
    print 'disconnected', ib.disconnect()
    sleep(1)
