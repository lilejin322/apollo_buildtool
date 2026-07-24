#/bin/bash

APOLLO_LIB_PATH="/opt/apollo/neo/lib"
LD_CACHE="/opt/apollo/neo/ld.cache"

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

if [ ! -e ${LD_CACHE} ]; then
    sudo touch ${LD_CACHE}
    sudo chmod a+w ${LD_CACHE}
fi

hash_val=`tree ${APOLLO_LIB_PATH} | sha256sum | awk '{print $1}'`
if [ ! "${hash_val}" = "`cat ${LD_CACHE}`" ]; then
    sudo echo "${hash_val}" > ${LD_CACHE}

    sudo touch /etc/ld.so.conf.d/apollo.conf
    sudo chmod a+w /etc/ld.so.conf.d/apollo.conf
    echo "">/etc/ld.so.conf.d/apollo.conf
    readdir $APOLLO_LIB_PATH
    sudo ldconfig 2>&1 >/dev/null
fi