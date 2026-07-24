#/bin/bash

APOLLO_LIB_PATH="/opt/apollo/neo/lib"
sudo touch /etc/ld.so.conf.d/apollo.conf
sudo chmod a+w /etc/ld.so.conf.d/apollo.conf
echo "">/etc/ld.so.conf.d/apollo.conf

readdir() {
  for file in `ls -r $1`
    do
        if [ -d $1/$file ];then
            echo "$1/$file" >> /etc/ld.so.conf.d/apollo.conf
            cd $1/$file
            readdir $1"/"$file
            cd -
        fi
    done
}

readdir $APOLLO_LIB_PATH
sudo ldconfig 2>&1 >/dev/null