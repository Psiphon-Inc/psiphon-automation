#!/bin/bash
echo $(curl -s http://169.254.169.254/latest/meta-data/instance-id)
echo $(curl -s http://169.254.169.254/latest/meta-data/instance-type)
echo $(curl -s http://169.254.169.254/latest/meta-data/ami-id)
