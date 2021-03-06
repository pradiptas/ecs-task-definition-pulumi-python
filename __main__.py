"""An AWS Python Pulumi program"""
import pulumi
import pulumi_aws as aws
import json
...
# Create an AWS resource (ECS Cluster)
cluster = aws.ecs.Cluster("ecs-pulumi-cluster-3")
container_secret = aws.secretsmanager.get_secret(arn="arn:aws:secretsmanager:us-west-2:272603463567:secret:prad_secret-1emAvr")

...
# Create Load Balancer

vpc = aws.ec2.get_vpc(default=True)
vpc_subnets = aws.ec2.get_subnet_ids(vpc_id=vpc.id)

group = aws.ec2.SecurityGroup(
    "pulumi-demo-secgroup",
    vpc_id=vpc.id,
    description='Enable HTTP access',
    ingress=[
        {'protocol': 'icmp', 'from_port': 8,
            'to_port': 0, 'cidr_blocks': ['0.0.0.0/0']},
        {'protocol': 'tcp', 'from_port': 80,
            'to_port': 80, 'cidr_blocks': ['0.0.0.0/0']}
    ],
    egress=[
        {'protocol': "-1", 'from_port': 0,
            'to_port': 0, 'cidr_blocks': ['0.0.0.0/0']}
    ])

alb = aws.lb.LoadBalancer(
    "pulumi-demo-lb",
    internal="false",
    security_groups=[group.id],
    subnets=vpc_subnets.ids,
    load_balancer_type="application",
)

atg = aws.lb.TargetGroup(
    "pulumi-demo-tg",
    port=80,
    deregistration_delay=0,
    protocol="HTTP",
    target_type="ip",
    vpc_id=vpc.id,
)

wl = aws.lb.Listener(
    "pulumi-demo",
    load_balancer_arn=alb.arn,
    port=80,
    default_actions=[{"type": "forward", "target_group_arn": atg.arn}],
)

...
# IAM Role

role = aws.iam.Role("task-exec-role",
                    assume_role_policy=json.dumps({
                        "Version": "2008-10-17",
                        "Statement": [{
                            "Sid": "",
                            "Effect": "Allow",
                            "Principal": {
                                "Service": "ecs-tasks.amazonaws.com"
                            },
                            "Action": "sts:AssumeRole"
                        }]
                    }))

rpa = aws.iam.RolePolicyAttachment("task-exec-policy",
                                   role=role.name,
                                   policy_arn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
                                   )
...
# task definition
task_definition = aws.ecs.TaskDefinition("pulumi-demo-task",
                                         family="fargate-task-definition",
                                         cpu="256",
                                         memory="512",
                                         network_mode="awsvpc",
                                         requires_compatibilities=["FARGATE"],
                                         execution_role_arn=role.arn,
                                         container_definitions=json.dumps([{
                                             "name": "pulumi-demo-app",
                                             "image": "272603463567.dkr.ecr.us-west-2.amazonaws.com/ecr-devops-pradipta",
                                             "secrets": [{
                                                    "Name" : "prad_secret",
                                                    "ValueFrom": container_secret
                                             }],
                                             "environment": [{
                                                    "pradenv" : "env-value"
                                             }],
                                             "portMappings": [{
                                                 "containerPort": 80,
                                                 "hostPort": 80,
                                                 "protocol": "tcp"
                                             }]
                                         }])
                                         )

service = aws.ecs.Service("pulumi-demo-svc",
                          cluster=cluster.arn,
                          desired_count=3,
                          launch_type="FARGATE",
                          task_definition=task_definition.arn,
                          network_configuration={
                              "assign_public_ip": "true",
                              "subnets": vpc_subnets.ids,
                              "security_groups": [group.id]
                          },
                          load_balancers=[{
                              "target_group_arn": atg.arn,
                              "container_name": "pulumi-demo-app",
                              "container_port": 80
                          }],
                          opts=pulumi.ResourceOptions(depends_on=[wl])
                          )

pulumi.export("url", alb.dns_name)
