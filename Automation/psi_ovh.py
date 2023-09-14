

import ovh
import json
import random



#==============================================================================
###
#
# General API Interaction functions
#
###

class PsiOVH:
  def __init__(self, ovh_account, debug=False):
    # ovh-us has the most subsidiaries
    # ['ASIA', 'AU', 'CA', 'CZ', 'DE', 'ES', 'EU', 'FI', 'FR', 'GB', 'IE', 'IT', 'LT', 'MA', 'NL', 'PL', 'PT', 'QC', 'SG', 'SN', 'TN', 'US', 'WE', 'WS']
    # But will require using different application_key
    self.api_endpoint = ovh_account.api_endpoints # Possible endpoint ['ovh-ca', 'ovh-us', 'ovh-eu']
    self.ovh_subsidiary = ovh_account.api_subsidiaries # Possible SubSidiary for ovh-ca ['ASIA', 'AU', 'CA', 'IN', 'QC', 'SG', 'WE', 'WS']

    self.client = ovh.Client(
      endpoint=self.api_endpoint,
      application_key=ovh_account.api_application_key,
      application_secret=ovh_account.api_application_secret,
      consumer_key=ovh_account.api_consumer_key
    )

  def get_region_by_datacenter(self, datacenter):
    if datacenter in ['bhs8']:
      region = 'CA'
    elif datacenter in ['waw1']:
      region = 'PL'
    elif datacenter in ['lim3']:
      region = 'DE'
    elif datacenter in ['eri1']:
      region = 'GB'
    elif datacenter in ['gra3', 'rbx8', 'sbg5', 'gra2']:
      region = 'FR'

    return region

  def create_new_order_cart(self):
    order_cart = self.client.post('/order/cart',
                           ovhSubsidiary=self.ovh_subsidiary
                           )
    return order_cart['cartId']

  def checkout_order_cart(self, cart_id):
    res = self.client.post('/order/cart/{cartId}/assign'.format(cartId=cart_id))
    checkout_res = self.client.post('/order/cart/{cartId}/checkout'.format(cartId=cart_id),
                           autoPayWithPreferredPaymentMethod=True
                           )

    return checkout_res

  def order_new_ip_addresses(self, destination_server_ids=None, quantity=5):
    cart_id = self.create_new_order_cart()

    for destination_server_id in destination_server_ids:
      server = self.client.get('/dedicated/server/{serverId}'.format(serverId=destination_server_id))

      country = self.get_region_by_datacenter(server['datacenter'])
      print("Using IP Country: {}".format(country))

      if country in ['AU', 'CA', 'IN', 'SG']:
        plan_code = 'ip-failover-arin'
      elif country in ['BE', 'CH', 'CZ', 'DE', 'ES', 'FI', 'FR', 'IE', 'IT', 'LT', 'NL', 'PL', 'PT', 'UK']:
        plan_code = 'ip-failover-ripe'
      elif country in ['GB']:
        plan_code = 'ip-failover-ripe'
      else:
        print("IP Country not available to match plan_code...")

      print("Using PlanCode: {}".format(plan_code))
      ip_order = self.client.post('/order/cart/{cartId}/ip'.format(cartId=cart_id),
                             duration='P1M',
                             planCode=plan_code,
                             pricingMode='default',
                             quantity=quantity
                             )

      item_id = ip_order['itemId']

      ip_available_country = self.client.get('/order/cart/{cartId}/item/{itemId}/requiredConfiguration'.format(cartId=cart_id, itemId=ip_order['itemId']))[0]['allowedValues']

      if country in ip_available_country:
        ip_country = country
      elif country == 'GB':
        ip_country = 'UK'
      else:
        print("IP Country incorrect..")

      ip_config_country = self.client.post('/order/cart/{cartId}/item/{itemId}/configuration'.format(cartId=cart_id, itemId=item_id),
                                   label='country',
                                   value=ip_country
                                   )

      if plan_code == 'ip-failover-ripe':
        print("RIPE IP require destination servers, region: {}, destination: {}".format(ip_country, destination_server_id))
        ip_config_destination = self.client.post('/order/cart/{cartId}/item/{itemId}/configuration'.format(cartId=cart_id, itemId=item_id),
                                   label='destination',
                                   value=destination_server_id
                                   )

      print("Success setup cart order, CartID:{} and ItemID:{}".format(cart_id, item_id))

    checkout_order = self.checkout_order_cart(cart_id)

    return checkout_order['orderId']
