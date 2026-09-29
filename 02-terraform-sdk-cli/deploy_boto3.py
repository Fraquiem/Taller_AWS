#!/usr/bin/env python3
"""Create/destroy/verify the point-2 lab. Writes IDs only; never reads a password."""
import argparse, json, os, sys, time
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

STATE = Path(os.environ.get("BOTO3_STATE", "boto3-state.json"))
TAGS = [{"Key": k, "Value": v} for k, v in {"Project":"EIA-AWS-Activity", "Environment":"Lab", "ManagedBy":"OMP"}.items()]
def tag(ec2, resource_ids): ec2.create_tags(Resources=resource_ids, Tags=TAGS)
def main():
    p=argparse.ArgumentParser(); p.add_argument("action", choices=["create","destroy","verify"]); p.add_argument("--region", default="us-east-2"); p.add_argument("--trusted-cidr", default="127.0.0.1/32"); p.add_argument("--state", default=str(STATE)); a=p.parse_args()
    state_path=Path(a.state); session=boto3.Session(region_name=a.region); ec2=session.client("ec2"); s3=session.client("s3"); rds=session.client("rds")
    if a.action == "create":
        suffix=os.urandom(4).hex(); vpc=ec2.create_vpc(CidrBlock="10.42.0.0/16")["Vpc"]["VpcId"]; tag(ec2,[vpc]); ec2.modify_vpc_attribute(VpcId=vpc,EnableDnsSupport={"Value":True}); ec2.modify_vpc_attribute(VpcId=vpc,EnableDnsHostnames={"Value":True})
        igw=ec2.create_internet_gateway()["InternetGateway"]["InternetGatewayId"]; ec2.attach_internet_gateway(VpcId=vpc,InternetGatewayId=igw); tag(ec2,[igw])
        azs=ec2.describe_availability_zones(Filters=[{"Name":"state","Values":["available"]}])["AvailabilityZones"][:2]
        pub=ec2.create_subnet(VpcId=vpc,CidrBlock="10.42.1.0/24",AvailabilityZone=azs[0]["ZoneName"])["Subnet"]["SubnetId"]; priv=[]
        for i,az in enumerate(azs): priv.append(ec2.create_subnet(VpcId=vpc,CidrBlock=f"10.42.{10+i}.0/24",AvailabilityZone=az["ZoneName"])["Subnet"]["SubnetId"])
        rt=ec2.create_route_table(VpcId=vpc)["RouteTable"]["RouteTableId"]; ec2.create_route(RouteTableId=rt,DestinationCidrBlock="0.0.0.0/0",GatewayId=igw); ec2.associate_route_table(RouteTableId=rt,SubnetId=pub); ec2.modify_subnet_attribute(SubnetId=pub,MapPublicIpOnLaunch={"Value":True})
        sg=ec2.create_security_group(GroupName=f"eia-ec2-{suffix}",Description="Restricted lab EC2",VpcId=vpc)["GroupId"]; ec2.authorize_security_group_ingress(GroupId=sg,IpPermissions=[{"IpProtocol":"tcp","FromPort":22,"ToPort":22,"IpRanges":[{"CidrIp":a.trusted_cidr}]}])
        rsg=ec2.create_security_group(GroupName=f"eia-rds-{suffix}",Description="PostgreSQL from EC2",VpcId=vpc)["GroupId"]; ec2.authorize_security_group_ingress(GroupId=rsg,IpPermissions=[{"IpProtocol":"tcp","FromPort":5432,"ToPort":5432,"UserIdGroupPairs":[{"GroupId":sg}]}])
        tag(ec2,[pub,*priv,rt,sg,rsg]); bucket=f"eia-aws-activity-{suffix}"; s3.create_bucket(Bucket=bucket,CreateBucketConfiguration={"LocationConstraint":a.region}); s3.put_bucket_tagging(Bucket=bucket,Tagging={"TagSet":TAGS}); s3.put_public_access_block(Bucket=bucket,PublicAccessBlockConfiguration={"BlockPublicAcls":True,"BlockPublicPolicy":True,"IgnorePublicAcls":True,"RestrictPublicBuckets":True}); s3.put_bucket_encryption(Bucket=bucket,ServerSideEncryptionConfiguration={"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}); s3.put_bucket_lifecycle_configuration(Bucket=bucket,LifecycleConfiguration={"Rules":[{"ID":"expire-lab-objects","Status":"Enabled","Filter":{"Prefix":""},"Expiration":{"Days":7}}]})
        ami=ec2.describe_images(Owners=["amazon"],Filters=[{"Name":"name","Values":["al2023-ami-2023.*-x86_64"]},{"Name":"state","Values":["available"]}])["Images"]; ami=sorted(ami,key=lambda x:x["CreationDate"])[-1]["ImageId"]
        inst=ec2.run_instances(ImageId=ami,InstanceType="t3.micro",MinCount=1,MaxCount=1,SubnetId=pub,SecurityGroupIds=[sg],MetadataOptions={"HttpTokens":"required","HttpEndpoint":"enabled","HttpPutResponseHopLimit":1},BlockDeviceMappings=[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":8,"VolumeType":"gp3","Encrypted":True,"DeleteOnTermination":True}}])["Instances"][0]["InstanceId"]; tag(ec2,[inst])
        db=f"eia-lab-{suffix}"; rds.create_db_instance(DBInstanceIdentifier=db,Engine="postgres",EngineVersion="16",DBInstanceClass="db.t3.micro",AllocatedStorage=20,MaxAllocatedStorage=20,StorageType="gp3",StorageEncrypted=True,DBName="eia",MasterUsername="eiaadmin",ManageMasterUserPassword=True,DBSubnetGroupName=rds.create_db_subnet_group(DBSubnetGroupName=db,DBSubnetGroupDescription="lab",SubnetIds=priv)["DBSubnetGroup"]["DBSubnetGroupName"],VpcSecurityGroupIds=[rsg],PubliclyAccessible=False,BackupRetentionPeriod=0,MultiAZ=False,DeletionProtection=False)
        state={"vpc":vpc,"igw":igw,"public_subnet":pub,"private_subnets":priv,"route_table":rt,"ec2_sg":sg,"rds_sg":rsg,"bucket":bucket,"instance":inst,"db":db,"db_subnet_group":db,"region":a.region}; state_path.write_text(json.dumps(state,indent=2)+"\n"); print(json.dumps({"created":True,"bucket":bucket,"instance":inst,"db":db}))
    elif a.action == "verify":
        st=json.loads(state_path.read_text()); s3.head_bucket(Bucket=st["bucket"]); print(json.dumps({"bucket":True,"instance":ec2.describe_instances(InstanceIds=[st["instance"]])["Reservations"][0]["Instances"][0]["State"]["Name"],"db":rds.describe_db_instances(DBInstanceIdentifier=st["db"])["DBInstances"][0]["DBInstanceStatus"]}))
    else:
        st=json.loads(state_path.read_text()); rds.delete_db_instance(DBInstanceIdentifier=st["db"],SkipFinalSnapshot=True,DeleteAutomatedBackups=True); rds.get_waiter("db_instance_deleted").wait(DBInstanceIdentifier=st["db"]); rds.delete_db_subnet_group(DBSubnetGroupName=st["db_subnet_group"]); ec2.terminate_instances(InstanceIds=[st["instance"]]); ec2.get_waiter("instance_terminated").wait(InstanceIds=[st["instance"]]);
        for obj in s3.list_objects_v2(Bucket=st["bucket"]).get("Contents",[]): s3.delete_object(Bucket=st["bucket"],Key=obj["Key"])
        s3.delete_bucket(Bucket=st["bucket"]); ec2.delete_security_group(GroupId=st["rds_sg"]); ec2.delete_security_group(GroupId=st["ec2_sg"]); ec2.disassociate_route_table(AssociationId=ec2.describe_route_tables(RouteTableIds=[st["route_table"]])["RouteTables"][0]["Associations"][0]["RouteTableAssociationId"]); ec2.delete_route_table(RouteTableId=st["route_table"])
        for subnet in [st["public_subnet"],*st["private_subnets"]]: ec2.delete_subnet(SubnetId=subnet)
        ec2.detach_internet_gateway(InternetGatewayId=st["igw"],VpcId=st["vpc"]); ec2.delete_internet_gateway(InternetGatewayId=st["igw"]); ec2.delete_vpc(VpcId=st["vpc"]); state_path.unlink(); print(json.dumps({"destroyed":True}))
    return 0
if __name__ == "__main__": sys.exit(main())
